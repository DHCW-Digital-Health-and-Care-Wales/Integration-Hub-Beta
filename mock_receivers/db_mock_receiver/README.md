# DB Mock Receiver (`db_mock_receiver`)

**Local testing only.** A real SQL Server container hosting a mock WRRS `DRS` database and a mock
`dbo.prQueueMessage` stored procedure, so `senders/db_sender` can be exercised end to end in the
`risp-to-wrrs` flow without a real WRRS database. It is not deployed to Azure.

## Contract of the mock procedure

Mirrors the real procedure:

| Outcome | Behaviour |
|---|---|
| Success | Returns nothing (return code `0`, no result set). The message is stored in `dbo.QueueMessage`. |
| Failure | `RETURN 55555` - a return code, **no SQL error is raised**. Nothing is stored. |

Parameters: `@Message VARCHAR(MAX)`, `@IsPriority BIT = 0`.

> **Known `db_sender` limitation:** the sender currently ignores the procedure's return code, so a
> `REJECT` scenario is logged as "executed successfully" and the message is completed (it is not dead-lettered).
> The mock reproduces the real contract faithfully; it is the sender that needs to honour the return code.

## Scenarios

Pick a scenario per message by including a token anywhere in the (synthetic) message body, e.g. in an XML
comment `<!-- MOCK_SCENARIO=REJECT -->`, or force one for every call with the global switch. A token overrides the switch.

| Scenario | Trigger | Procedure behaviour | Expected `db_sender` outcome |
|---|---|---|---|
| Success | none (default) | Stores the message, returns nothing | Message completed |
| `REJECT` | `MOCK_SCENARIO=REJECT` | `RETURN 55555` | Currently treated as success (see limitation above) |
| `ERROR` | `MOCK_SCENARIO=ERROR` | `THROW 50001` (SQL error) | Fatal -> dead-lettered |
| `TIMEOUT` | `MOCK_SCENARIO=TIMEOUT` | `WAITFOR DELAY '00:01:30'` (longer than the sender's default 60s `DB_COMMAND_TIMEOUT`) | Query timeout -> transient -> abandoned and retried |
| Invalid XML | message that is not XML | Cannot be stored -> `RETURN 55555` | As `REJECT` |
| DB down | `docker stop mock-db-receiver` | Connection failure | Transient -> retried |

Never put real patient data in test messages.

## Running it

From `local/` (needs `just secrets` first; the SA password comes from `local/.secrets`):

```bash
docker compose --profile risp-to-wrrs up -d mock-db-receiver wrrs-stmsg-dbsender
```

`mock-db-receiver` only reports healthy once `DRS` and `dbo.prQueueMessage` exist, and the sender waits for that.
The sender connects with `DB_SERVER=mock-db-receiver` (see `local/env/senders/wrrs-stmsg-dbsender.env`).
SQL Server is also published on the host at `localhost,14334` (user `sa`).

The image is `linux/amd64` only; on Apple Silicon it runs under emulation (the compose file sets the platform),
and Docker needs at least 2 GB RAM. First start takes roughly a minute.

## Inspecting and controlling the mock

```bash
# Run a query (set -a; . ./.secrets; set +a  first, to load MSSQL_SA_PASSWORD)
sql() { docker exec -e P="$MSSQL_SA_PASSWORD" mock-db-receiver bash -c \
  '/opt/mssql-tools18/bin/sqlcmd -C -b -S localhost -U sa -P "$P" -d DRS -W -Q "$0"' "$1"; }

sql "SELECT Id, ReceivedAtUtc, IsPriority, LEFT(Message, 120) AS Msg FROM dbo.QueueMessage"   # what was received
sql "UPDATE dbo.MockControl SET Scenario = 'REJECT'"   # force a scenario: NONE | REJECT | ERROR | TIMEOUT
sql "UPDATE dbo.MockControl SET Scenario = 'NONE'"     # back to normal
sql "DELETE FROM dbo.QueueMessage"                      # clear stored messages
```

Data is ephemeral: it is reset whenever the container is recreated.

## Files

| File | Purpose |
|---|---|
| `Dockerfile` | `mcr.microsoft.com/mssql/server:2022-latest` plus the init script and entrypoint |
| `entrypoint.sh` | Starts SQL Server, waits until ready, applies `sql/init.sql` |
| `sql/init.sql` | Idempotent creation of `DRS`, `dbo.QueueMessage`, `dbo.MockControl` and `dbo.prQueueMessage` |

Configuration lives in `local/env/mock_receivers/db-mock-receiver.env` (`ACCEPT_EULA`, `MSSQL_MEMORY_LIMIT_MB`);
`MSSQL_SA_PASSWORD` comes from `local/.secrets`.

## Design notes

See `Notes/mock_db_receiver.md` for the options considered (SQL Server container, Rust `mssql-mock-tds`,
Azure SQL) and why a real SQL Server container was chosen for local use: it needs no changes to the sender,
exercises the real ODBC/TDS path, and supports per-message scenarios and inspection of what was received.
