# Message Replay Job

A containerised job that replays HL7 messages from SQL Server to an Azure Service Bus priority queue. It is triggered manually by the support team when messages need to be re-processed.

## How It Works

1. Reads the `REPLAY_BATCH_ID` (UUID) from environment variables to identify the replay batch. This should be passed in to the container app job as well when triggered.
2. Fetches pending/failed rows from `monitoring.MessageReplayQueue` in configurable-sized batches (default 100), joined with `monitoring.Message` to retrieve the raw HL7 payload.
3. Sends each batch to the configured Service Bus priority queue via `MessageSenderClient` from the shared lib.
4. Marks each batch as `Loaded` in the database after successful send.
5. Repeats until no pending rows remain, then exits.

> [!IMPORTANT]
> All database and Service Bus operations use a **retry-once** strategy: if the first attempt fails, a single retry is made before aborting (or marking the batch as `Failed` for send errors).

## Configuration

| Environment Variable            | Required | Default | Description                                            |
| ------------------------------- | -------- | ------- | ------------------------------------------------------ |
| `REPLAY_BATCH_ID`               | Yes      | —       | UUID identifying the replay batch to process           |
| `REPLAY_BATCH_SIZE`             | No       | `100`   | Number of rows fetched per database round-trip         |
| `PRIORITY_QUEUE_NAME`           | Yes      | —       | Service Bus queue to send replayed messages to         |
| `SERVICE_BUS_CONNECTION_STRING` | No\*     | —       | Service Bus connection string (local dev)              |
| `SERVICE_BUS_NAMESPACE`         | No\*     | —       | Service Bus namespace (production, with MI)            |
| `SQL_SERVER`                    | Yes      | —       | SQL Server host (e.g. `localhost,1433`)                |
| `SQL_DATABASE`                  | Yes      | —       | Database name                                          |
| `SQL_USERNAME`                  | No       | —       | SQL username (local dev, requires `MSSQL_SA_PASSWORD`) |
| `MSSQL_SA_PASSWORD`             | No       | —       | SQL password (local dev, requires `SQL_USERNAME`)      |
| `SQL_ENCRYPT`                   | No       | `Yes`   | Whether to encrypt the SQL connection                  |
| `SQL_TRUST_SERVER_CERTIFICATE`  | No       | `No`    | Whether to trust the server certificate                |
| `MANAGED_IDENTITY_CLIENT_ID`    | No       | —       | Client ID for user-assigned Managed Identity           |

\* One of `SERVICE_BUS_CONNECTION_STRING` or `SERVICE_BUS_NAMESPACE` is needed.

### Build / checks

In the [message_replay_job](.) folder, to create a virtual environment and install project dependencies:

```bash
uv sync
```

Run code quality checks:

```bash
uv run ruff check
uv run bandit message_replay_job/**/*.py tests/**/*.py
uv run mypy --ignore-missing-imports message_replay_job/**/*.py tests/**/*.py
```

Run unit tests:

```bash
uv run python -m unittest discover tests
```

## REPLAY_BATCH_SIZE Tuning

The `REPLAY_BATCH_SIZE` env variable controls how many rows are fetched per database round-trip, mapping to `TOP (?)` in the fetch query. The default is currently set to 100, which is conservative given the typical HL7 message sizes expected currently.

A comparison between smaller and larger batch sizes below and the impact they have:

| Smaller batch size                                     | Larger batch size                          |
| ------------------------------------------------------ | ------------------------------------------ |
| More DB round-trips                                    | Fewer DB round-trips                       |
| Finer progress granularity                             | Coarser progress granularity               |
| Less memory usage                                      | More memory usage                          |
| Less likely to trigger Service Bus sub-batch splitting | More likely to trigger sub-batch splitting |

For large replay batches (thousands of messages), the support team can increase the value to reduce database round-trips using the REPLAY_BATCH_SIZE environment variable.

## Known Duplication Scenarios

The replay job provides **at-least-once** delivery. Duplicate messages on the priority queue are possible in the following scenarios and at this stage should be handled via manual deduplication by the support team.

The likelihood of this happening is low, however to aid deduplication each message carries a ReplayId and MessageId as application properties.
