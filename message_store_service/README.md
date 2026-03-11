# Message Store Service

Message storage service that reads HL7 messages from an Azure Service Bus queue and stores them in an Azure SQL
database for auditing and replaying purposes.

## Architecture

The service consumes messages from a Service Bus queue in configurable batches. For each batch, it:

1. Deserialises the JSON message body into a `MessageRecord`.
2. Batch-inserts all records into the `monitoring.Message` table using `pyodbc` with `fast_executemany`.
3. Acknowledges (completes) the batch only after a successful database commit.
4. On failure, rolls back the transaction and abandons the batch so messages are re-queued automatically.

The `DatabaseClient` maintains a single persistent connection that is opened lazily on first use and reused across
batches. If a database error occurs, the stale connection is discarded and transparently re-established on the next
batch.

### Database table — `monitoring.Message`

| Column                | Type            | Required | Description                                      |
| --------------------- | --------------- | -------- | ------------------------------------------------ |
| `ReceivedAt`          | `datetime`      | ✅       | Timestamp the message was originally received    |
| `StoredAt`            | `datetime`      | ✅       | Timestamp the record was written to the database |
| `CorrelationId`       | `nvarchar`      | ✅       | Unique identifier for tracing the message        |
| `SourceSystem`        | `nvarchar`      | ✅       | System that originated the message               |
| `ProcessingComponent` | `nvarchar`      | ✅       | Microservice that processed the message          |
| `TargetSystem`        | `nvarchar`      | ❌       | Destination system (if known)                    |
| `RawPayload`          | `nvarchar(max)` | ✅       | Original HL7 raw message payload                 |
| `XmlPayload`          | `nvarchar(max)` | ❌       | XML-transformed payload (if available)           |

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
  "XmlPayload": "<ClinicalDocument>...</ClinicalDocument>"
}
```

> `TargetSystem` and `XmlPayload` are optional.

## Development

### Dependencies

- [uv](https://docs.astral.sh/uv/) - Python package and project manager
- macOS: `brew install uv`
- Other platforms: See [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/)
- [ODBC Driver 18 for SQL Server](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server) — required at runtime for database connectivity

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

#### SQL database

| Variable                       | Required | Default | Description                                                                                                                            |
| ------------------------------ | -------- | ------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `SQL_SERVER`                   | ✅       | —       | SQL Server hostname or FQDN                                                                                                            |
| `SQL_DATABASE`                 | ✅       | —       | Target database name                                                                                                                   |
| `SQL_ENCRYPT`                  | ❌       | `Yes`   | Enable TLS encryption — use `Yes` / `No`. Defaults to `Yes` (secure for Azure SQL)                                                     |
| `SQL_TRUST_SERVER_CERTIFICATE` | ❌       | `No`    | Trust self-signed certificates — use `Yes` / `No`. Defaults to `No` (validates cert in prod); set to `Yes` for local dev               |
| `SQL_USERNAME`                 | ❌       | —       | SQL username — required for **password auth** (local dev); must be set together with `MSSQL_SA_PASSWORD`                               |
| `MSSQL_SA_PASSWORD`            | ❌       | —       | SQL password — required for **password auth** (local dev); must be set together with `SQL_USERNAME`; omit both to use Managed Identity |
| `MANAGED_IDENTITY_CLIENT_ID`   | ❌       | —       | Client ID of a **user-assigned** Managed Identity; omit to use the system-assigned identity                                            |

**Note:** This service does not use Service Bus sessions.

### Authentication modes

`SQL_USERNAME` and `MSSQL_SA_PASSWORD` must always be set together — providing only one will cause startup to fail with a clear error. Omit both to use Managed Identity.

#### Password auth (local development)

Set both `SQL_USERNAME` and `MSSQL_SA_PASSWORD`. The service connects via standard SQL Server username/password auth.

Also set `SQL_ENCRYPT=No` and `SQL_TRUST_SERVER_CERTIFICATE=Yes` to match the plain local SQL Server container (no TLS certificate configured).

#### Managed Identity auth (production / Azure)

Leave both `SQL_USERNAME` and `MSSQL_SA_PASSWORD` unset. The service authenticates via `Authentication=ActiveDirectoryMsi` in the ODBC
connection string.

`SQL_ENCRYPT` and `SQL_TRUST_SERVER_CERTIFICATE` default to `Yes` and `No` respectively.

- **System-assigned identity**: leave `MANAGED_IDENTITY_CLIENT_ID` unset — the driver picks up the single assigned identity automatically.
- **User-assigned identity**: set `MANAGED_IDENTITY_CLIENT_ID` to the client ID of the target identity so the driver selects the correct one.

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
