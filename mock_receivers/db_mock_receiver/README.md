# DB Mock Receiver (`db_mock_receiver`)

**Local testing and Azure DEV only.** A real SQL Server container hosting a mock WRRS `DRS` database and mock
`dbo.prQueueMessage` and `dbo.prQueueIdUpdate` stored procedures, so `senders/db_sender` can be exercised end to end
in the `risp-to-wrrs` (`wrrs-stmsg-dbsender`) and `lims-to-wrrs` (`wrrs-idupd-dbsender`) flows without a real WRRS
database. It must never be deployed to a production-like environment.

## Contract of the mock procedures

Both mirror the real procedures:

| Procedure | Used by | Parameters | Stores into |
|---|---|---|---|
| `dbo.prQueueMessage` | `wrrs-stmsg-dbsender` (RISP) | `@Message VARCHAR(MAX)`, `@IsPriority BIT = 0` | `dbo.QueueMessage` |
| `dbo.prQueueIdUpdate` | `wrrs-idupd-dbsender` (LIMS) | `@ProviderPatientIdentifier`, `@ProviderAssigningAuthority`, `@OldIdentifier`, `@OldIdentifierAssigningAuthority`, `@NewIdentifier`, `@NewIdentifierAssigningAuthority` (the last two are required) | `dbo.QueueIdUpdate` |

| Outcome | Behaviour |
|---|---|
| Success | Returns nothing (return code `0`, no result set). The data is stored. |
| Failure (`REJECT`) | `RETURN 55555` - a return code, **no SQL error is raised**. Nothing is stored. |

`db_sender` reads the return code: any non-zero value (or a missing one) is rolled back and treated as a fatal
error, so the message is dead-lettered exactly as if the procedure had raised a SQL error.

## Scenarios

Force a scenario for every call to either procedure with the global switch (`dbo.MockControl`), or pick one per
message:

- `prQueueMessage`: include a token anywhere in the (synthetic) message body, e.g. an XML comment
  `<!-- MOCK_SCENARIO=REJECT -->`.
- `prQueueIdUpdate`: use a sentinel as the new identifier (`MOCK_REJECT`, `MOCK_ERROR`, `MOCK_TIMEOUT`).

A per-message trigger overrides the switch.

| Scenario | Trigger (`prQueueMessage` / `prQueueIdUpdate`) | Procedure behaviour | Expected `db_sender` outcome |
|---|---|---|---|
| Success | none (default) | Stores the data, returns nothing | Message completed |
| `REJECT` | `MOCK_SCENARIO=REJECT` / new identifier `MOCK_REJECT` | `RETURN 55555` | Non-zero return code -> fatal -> dead-lettered |
| `ERROR` | `MOCK_SCENARIO=ERROR` / new identifier `MOCK_ERROR` | `THROW 50001` (SQL error) | Fatal -> dead-lettered |
| `TIMEOUT` | `MOCK_SCENARIO=TIMEOUT` / new identifier `MOCK_TIMEOUT` | `WAITFOR DELAY '00:01:30'` (longer than the sender's default 60s `DB_COMMAND_TIMEOUT`) | Query timeout -> transient -> abandoned and retried |
| Invalid XML | `prQueueMessage` only: message that is not XML | Cannot be stored -> `RETURN 55555` | As `REJECT` |
| DB down | `docker stop mock-db-receiver` | Connection failure | Transient -> retried |

Never put real patient data in test messages.

## Running it

From `local/` (needs `just secrets` first; the SA password comes from `local/.secrets`):

```bash
docker compose --profile risp-to-wrrs up -d mock-db-receiver wrrs-stmsg-dbsender
docker compose --profile lims-to-wrrs up -d mock-db-receiver wrrs-idupd-dbsender
```

`mock-db-receiver` only reports healthy once `DRS`, `dbo.prQueueMessage` and `dbo.prQueueIdUpdate` exist, and the
senders wait for that. They connect with `DB_SERVER=mock-db-receiver` (see `local/env/senders/wrrs-stmsg-dbsender.env`
and `local/env/senders/wrrs-idupd-dbsender.env`).
SQL Server is also published on the host at `localhost,14334` (user `sa`).

The image is `linux/amd64` only; on Apple Silicon it runs under emulation (the compose file sets the platform),
and Docker needs at least 2 GB RAM. First start takes roughly a minute.

## Inspecting and controlling the mock

```bash
# Run a query (set -a; . ./.secrets; set +a  first, to load MSSQL_SA_PASSWORD)
sql() { docker exec -e P="$MSSQL_SA_PASSWORD" mock-db-receiver bash -c \
  '/opt/mssql-tools18/bin/sqlcmd -C -b -S localhost -U sa -P "$P" -d DRS -W -Q "$0"' "$1"; }RISP: what was received
sql "SELECT * FROM dbo.QueueIdUpdate ORDER BY Id"      # LIMS: identifier updates received
sql "UPDATE dbo.MockControl SET Scenario = 'REJECT'"   # force a scenario: NONE | REJECT | ERROR | TIMEOUT
sql "UPDATE dbo.MockControl SET Scenario = 'NONE'"     # back to normal
sql "DELETE FROM dbo.QueueMessage; DELETE FROM dbo.QueueIdUpdate"   # clear stored data | REJECT | ERROR | TIMEOUT
sql "UPDATE dbo.MockControl SET Scenario = 'NONE'"     # back to normal
sql "DELETE FROM dbo.QueueMessage"                      # clear stored messages
```

Data is ephemeral: it is reset whenever the container is recreated.

## Deploying to Azure DEV

Runs as the Azure Container App `uks-dev-dbmockreceiver-ca`, defined in `Integration-Hub-Terraform`
(`components/app-platform/flow_shared_apps.tf`, flag `deploy_db_mock_receiver`, DEV only).

| Aspect | Setting |
|---|---|
| Image | `uksdhcwihsharedcr.azurecr.io/dbmockreceiver:dev`, built by `pipeline-ado/dbmockreceiver-build.yml` and released with the `DB Mock Receiver` entry in `release-apps.yml` (DEV only) |
| Size | 1 vCPU / 2 GiB (SQL Server will not start with less than 2 GB); about 0.85 GiB used at idle |
| Replicas | Exactly 1, no scale rules. Data is ephemeral and is lost on every restart or new revision |
| Ingress | TCP on 1433 with `external_enabled = true`. The Container Apps environment uses an internal load balancer, so this means reachable from the VNet (the DB senders and the pipeline agents that verify the LIMS to WRRS flow), **not** from the internet. The `sa` login is protected only by the `wrrs-db-password` secret, so the mock must stay DEV only (Terraform enforces this with a precondition) |
| Edition | `MSSQL_PID=Express`, which is free to use in any environment (the, `dbo.prQueueMessage` and `dbo.prQueueIdUpdation is non-production only) |
| Probes | TCP on 1433. Port 1433 is only opened by the entrypoint once `DRS` and `dbo.prQueueMessage` exist (the real SQL Server listens on loopback port 14330 and `socat` forwards 1433 afterwards), so a TCP probe is effectively schema-aware. While the mock is starting or restarting, clients get connection refused, which `db_sender` treats as transient and retries. Without this gate a client that connected early would hit a missing database or procedure, which `db_sender` classifies as **fatal** and dead-letters |
| TLS | SQL Server presents a self-signed certificate, so the sender runs with `DB_ENCRYPT=yes` and `DB_TRUST_SERVER_CERTIFICATE=yes` (Terraform sets this automatically when the mock is deployed). Without it the driver fails with `08001 ... self-signed certificate`, which the sender treats as transient, so it would retry forever |
| Sender target | `DB_SERVER` is the app name `uks-dev-dbmockreceiver-ca`, port 1433 (set by Terraform instead of the `wrrs-db-server` secret) |

### One-off setup before the first deploy

1. **Key Vault secrets** in the shared Key Vault. The mock and the sender share them:
   - `wrrs-db-username` = `sa`
   - `wrrs-db-password` = a strong password. SQL Server requires 8+ characters with 3 of: upper case, lower case, digit, symbol.
     A password that does not meet the policy makes SQL Server exit and the container restart-loop.
   - `wrrs-db-server` is not needed while the mock is deployed.
2. **Create the `DB Mock Receiver - Build` pipeline** in Azure DevOps from `pipeline-ado/dbmockreceiver-build.yml`. Release
   refers to it by that name.
3. **Build and release** the image (`DB Mock Receiver`, DEV), then apply Terraform with `deploy_risp_to_wrrs_flow = true`
   and `deploy_db_mock_receiver = true` in `environments/app-platform-dev.tfvars`.
   Release a new image after any change to `sql/init.sql`.

### Using it in DEV

There is no host port in Azure, so open a console in the container (portal: Container App > Monitoring > Console, or
`az containerapp exec`) and run `sqlcmd` there. The password is already in the `MSSQL_SA_PASSWORD` environment variable:

```bash
/opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -d DRS -Q "SELECT COUNT(*) FROM dbo.QueueMessage"
```

The queries under "Inspecting and controlling the mock" work the same way.

## Files

| File | Purpose |
|---|---|
| `Dockerfile` | `mcr.microsoft.com/mssql/server:2022-latest` plus `socat`, the init script and entrypoint |
| `entrypoint.sh` | Starts SQL Server on a loopback-only port, applies `sql/init.sql`, then opens port 1433 via `socat`; forwards stop signals for a clean shutdown |
| `sql/init.sql` | Idempotent creation of `DRS`, `dbo.QueueMessage`, `dbo.QueueIdUpdate`, `dbo.MockControl`, `dbo.prQueueMessage` and `dbo.prQueueIdUpdate` |

Configuration lives in `local/env/mock_receivers/db-mock-receiver.env` (`ACCEPT_EULA`, `MSSQL_MEMORY_LIMIT_MB`);
`MSSQL_SA_PASSWORD` comes from `local/.secrets`.

## Design notes

See `Notes/mock_db_receiver.md` for the options considered (SQL Server container, Rust `mssql-mock-tds`,
Azure SQL) and why a real SQL Server container was chosen for local use: it needs no changes to the sender,
exercises the real ODBC/TDS path, and supports per-message scenarios and inspection of what was received.
