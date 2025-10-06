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
- **INGRESS_SESSION_ID** - service bus queue FIFO session name (optional, sessions not used if not set)
- **RECEIVER_MLLP_HOST** - HL7/mllp destination server host
- **RECEIVER_MLLP_PORT** - HL7/mllp destination server port
- **ACK_TIMEOUT_SECONDS** - time for message acklowledgement
- **AUDIT_QUEUE_NAME** - service bus queue name for storing audit events
- **WORKFLOW_ID** - workflow id (used for audit)
- **MICROSERVICE_ID** - service id (used for audit)
- **HEALTH_CHECK_HOST** - default 127.0.0.1
- **health_check_port** - default 9000

### Running directly

From the [hl7_sender](.) folder run:

```sh
python -m hl7_sender.application
```

### Running in docker

You can build the docker image with provided [Dockerfile](./Dockerfile) or you can run selected workflow
using Docker compose configuration in [local](../local/README.md).
