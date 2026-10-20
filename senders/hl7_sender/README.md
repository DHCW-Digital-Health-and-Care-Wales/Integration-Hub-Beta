# HL7 Sender

HL7 Sender Service is a message delivery service that subscribes to transformed HL7 messages from the message bus and reliably delivers them to target systems (e.g., MPI - Master Patient Index). Handles connection management, retries, delivery acknowledgements, and error reporting to ensure end-to-end message delivery.

## Development

### Dependencies

- [uv](https://docs.astral.sh/uv/) - Python package and project manager
- macOS: `brew install uv`
- Other platforms: See [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/)

### Build / checks

In the [hl7_sender](.) folder, to create a virtual environment and install project dependencies:

```bash
uv sync
```

Run code quality checks:

```bash
uv run ruff check
uv run bandit -r hl7_sender/ tests/
uv run mypy --ignore-missing-imports hl7_sender/**/*.py
```

Run unit tests:

```bash
uv run python -m unittest discover tests
```

## Running HL7 sender

You can run the HL7 sender directly with python or build docker image and run it in the container.
Destination host and port should be configured using environment variables configuration.

### Environment variables

- **LOG_LEVEL** - default 'INFO'
- **SERVICE_BUS_CONNECTION_STRING** - service bus connection string (optional, required when SERVICE_BUS_NAMESPACE is empty)
- **SERVICE_BUS_NAMESPACE** - service bus namespace (recommended, required when SERVICE_BUS_CONNECTION_STRING is empty)
- **INGRESS_QUEUE_NAME** - service bus queue name to read messages from
- **INGRESS_TOPIC_NAME** / **INGRESS_SUBSCRIPTION_NAME** - service bus topic/subscription to read messages from (alternative to `INGRESS_QUEUE_NAME`; mutually exclusive with it)
- **INGRESS_SESSION_ID** - service bus queue FIFO session name (stored alongside each persisted message so the replay job can route replayed messages back through this sender). Mutually exclusive with `INGRESS_ACCEPT_ANY_SESSION`.
- **INGRESS_ACCEPT_ANY_SESSION** - set to `true` to accept messages from *any* session instead of a single fixed one (uses the Service Bus `NEXT_AVAILABLE_SESSION` filter). Use this when this sender's ingress is shared by multiple flows publishing under different session IDs, so multiple replicas can each lock a different flow's session concurrently instead of contending for one hardcoded session. The session actually set on each received message is used for message-store/replay routing in this mode, so `REPLAY_SESSION_ID` is not required. Mutually exclusive with `INGRESS_SESSION_ID`.
- **REPLAY_SESSION_ID** - Service Bus session ID stored for replay when ingress has no session ID; required when `MESSAGE_STORE_QUEUE_NAME` is set and neither `INGRESS_SESSION_ID` nor `INGRESS_ACCEPT_ANY_SESSION` is set
- **RECEIVER_MLLP_HOST** - HL7/mllp destination server host
- **RECEIVER_MLLP_PORT** - HL7/mllp destination server port
- **ACK_TIMEOUT_SECONDS** - time for message acklowledgement
- **MESSAGE_STORE_QUEUE_NAME** - Message store service bus queue (optional — message store persistence is skipped when unset)
- **MESSAGE_STORE_ENABLED** - Set to `true` (or any value other than `false`) to enable message store persistence (optional, default `false` — disabled)
- **WORKFLOW_ID** - workflow id (used for audit)
- **MICROSERVICE_ID** - service id (used for audit)
- **HEALTH_CHECK_HOST** - default 127.0.0.1
- **HEALTH_CHECK_PORT** - default 9000

### Running directly

From the [hl7_sender](.) folder run:

```sh
python -m hl7_sender.application
```

### Running in docker

You can build the docker image with provided [Dockerfile](./Dockerfile) or you can run selected workflow
using Docker compose configuration in [local](../local/README.md).
