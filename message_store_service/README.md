# Message Store Service

Message storage service that reads HL7 messages from an Azure Service Bus queue and stores them in a PostgreSQL
database for auditing and replaying purposes.

## Architecture

The service consumes messages from a Service Bus queue in configurable batches. For each batch, it:

1. Deserialises the JSON message body into a `MessageRecord`.
2. Batch-inserts all records into the `monitoring.message` table using `psycopg` with `executemany`.
3. Acknowledges (completes) the batch only after a successful database commit.
4. On failure, rolls back the transaction and abandons the batch so messages are re-queued automatically.

The `DatabaseClient` maintains a single persistent connection that is opened lazily on first use and reused across
batches. If a database error occurs, the stale connection is discarded and transparently re-established on the next
batch.

### Database table — `monitoring.message`

| Column                 | Type             | Required | Description                                       |
| ---------------------- | ---------------- | -------- |---------------------------------------------------|
| `received_at`          | `timestamptz(3)` | ✅       | Timestamp the message was originally received     |
| `stored_at`            | `timestamptz(3)` | ✅       | Timestamp the record was written to the database  |
| `correlation_id`       | `varchar(100)`   | ✅       | Unique identifier for tracing the message         |
| `source_system`        | `varchar(50)`    | ✅       | System that originated the message                |
| `processing_component` | `varchar(100)`   | ✅       | Microservice that processed the message           |
| `target_system`        | `varchar(50)`    | ❌       | Destination system (if known)                     |
| `raw_payload`          | `text`           | ✅       | Original HL7 raw message payload                  |
| `xml_payload`          | `xml`            | ❌       | XML-transformed payload (if available)            |
| `session_id`           | `varchar(128)`   | ✅       | Service Bus session ID of the storing component   |

> Identifiers are lower-case `snake_case` because PostgreSQL folds unquoted identifiers to lower case —
> using the original `PascalCase` names would require double-quoting every identifier in every query.

### Service Bus message format

Each Service Bus message body must be a JSON object with the following fields:

```json
{
  "MessageReceivedAt": "2026-02-25T10:00:00+00:00",
  "CorrelationId": "abc-123",
  "SourceSystem": "PIMS",
  "ProcessingComponent": "hl7_pims_transformer",
  "RawPayload": "MSH|...",
  "TargetSystem": "MPI",
  "XmlPayload": "<ClinicalDocument>...</ClinicalDocument>",
  "SessionId": "pims-to-mpi"
}
```

> `TargetSystem` and `XmlPayload` are optional. `SessionId` is required and is set by the producing component
> (`EGRESS_SESSION_ID` for `hl7_server`, `INGRESS_SESSION_ID` for `hl7_sender`).

## Development

### Dependencies

- [uv](https://docs.astral.sh/uv/) - Python package and project manager
- macOS: `brew install uv`
- Other platforms: See [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/)

> No native database driver needs installing: `psycopg[binary]` bundles its own libpq.

### Build / checks

In the [message_store_service](.) folder, to create a virtual environment and install project dependencies:

```bash
uv sync
```

Run code quality checks:

```bash
uv run ruff check
uv run bandit message_store_service/**/*.py tests/**/*.py
uv run mypy --ignore-missing-imports message_store_service/**/*.py tests/**/*.py
```

Run unit tests:

```bash
uv run python -m unittest discover tests
```

## Running Message Store Service

You can run the service directly with python or build docker image and run it in the container.

### Environment variables

#### Service Bus

| Variable                        | Required | Default | Description                                                                                 |
| ------------------------------- | -------- | ------- | ------------------------------------------------------------------------------------------- |
| `SERVICE_BUS_CONNECTION_STRING` | ⚠️       | —       | Service Bus connection string (required when `SERVICE_BUS_NAMESPACE` is empty)              |
| `SERVICE_BUS_NAMESPACE`         | ⚠️       | —       | Service Bus namespace (recommended; required when `SERVICE_BUS_CONNECTION_STRING` is empty) |
| `INGRESS_QUEUE_NAME`            | ✅       | —       | Queue name to read messages from                                                            |

#### Service identity & health

| Variable            | Required | Default     | Description                       |
| ------------------- | -------- | ----------- | --------------------------------- |
| `MICROSERVICE_ID`   | ✅       | —           | Service ID used for audit logging |
| `LOG_LEVEL`         | ❌       | `INFO`      | Python logging level              |
| `AZURE_LOG_LEVEL`   | ❌       | `WARN`      | Log level for the Azure SDK       |
| `HEALTH_CHECK_HOST` | ❌       | `127.0.0.1` | TCP health-check bind address     |
| `HEALTH_CHECK_PORT` | ❌       | `9000`      | TCP health-check port             |

#### PostgreSQL database

| Variable                     | Required | Default   | Description                                                                                                          |
| ---------------------------- | -------- | --------- | -------------------------------------------------------------------------------------------------------------------- |
| `PG_HOST`                    | ✅       | —         | PostgreSQL hostname or FQDN                                                                                          |
| `PG_DATABASE`                | ✅       | —         | Target database name                                                                                                 |
| `PG_USER`                    | ✅       | —         | Database role name — required in **both** auth modes                                                                 |
| `PG_PORT`                    | ❌       | `5432`    | PostgreSQL port                                                                                                      |
| `PG_SSLMODE`                 | ❌       | `require` | libpq SSL mode. Defaults to `require` (secure for Azure); set to `disable` for the local container                    |
| `POSTGRES_PASSWORD`          | ❌       | —         | Database password — set for **password auth** (local dev); omit to use Managed Identity                              |
| `MANAGED_IDENTITY_CLIENT_ID` | ❌       | —         | Client ID of a **user-assigned** Managed Identity; omit to use the system-assigned identity                          |

**Note:** This service does not use Service Bus sessions.

### Authentication modes

`PG_USER` is always required. Unlike SQL Server's `ActiveDirectoryMsi` mode, PostgreSQL needs a role name even when
authenticating with an Entra token — only the password differs between the two modes.

#### Password auth (local development)

Set `POSTGRES_PASSWORD`. The service connects with standard PostgreSQL password auth.

Also set `PG_SSLMODE=disable` to match the plain local PostgreSQL container (no TLS certificate configured).

`POSTGRES_PASSWORD` is deliberately named after the variable the `postgres` container image itself reads, so a single
secret drives both the server and its clients in local development.

#### Managed Identity auth (production / Azure)

Leave `POSTGRES_PASSWORD` unset. The service acquires an Entra access token for
`https://ossrdbms-aad.database.windows.net/.default` via `ManagedIdentityCredential` and passes it as the connection
password. A fresh token is acquired on every connect, so expiry is handled by the existing reconnect logic.

`PG_SSLMODE` defaults to `require`.

- **System-assigned identity**: leave `MANAGED_IDENTITY_CLIENT_ID` unset.
- **User-assigned identity**: set `MANAGED_IDENTITY_CLIENT_ID` to the client ID of the target identity.

> The Entra role must exist in the database. Azure Database for PostgreSQL requires an in-database
> `pgaadauth_create_principal` call — this cannot be done from Terraform.

### Running directly

From the `message_store_service` folder run:

```sh
python -m message_store_service.application
```

### Running in docker

You can build the docker image with provided [Dockerfile](./Dockerfile) or you can run the service
using Docker compose configuration in [local](../local/README.md).

### Batch size

The maximum number of messages processed per batch is controlled by `max_batch_size` in
[`config.ini`](message_store_service/config.ini) (default: `100`). Each batch is committed as a single atomic
database transaction.
