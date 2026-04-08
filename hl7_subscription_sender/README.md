# HL7 Subscription Sender

 HL7 Subscription Sender service is a message delivery service that subscribes to HL7 messages from the message bus and reliably delivers them to target systems. It handles connection management, retries, delivery acknowledgements, and error reporting to ensure end-to-end message delivery.

## Development

### Dependencies

- [uv](https://docs.astral.sh/uv/) - Python package and project manager
- macOS: `brew install uv`
- Other platforms: See [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/)

### Build / checks

In the [hl7_subscription_sender](.) folder, to create a virtual environment and install project dependencies:

```bash
uv sync
```

Run code quality checks:

```bash
uv run ruff check
uv run bandit -r hl7_subscription_sender/ tests/
uv run mypy --ignore-missing-imports hl7_subscription_sender/**/*.py
```

Run unit tests:

```bash
uv run python -m unittest discover tests
```

## Running HL7 subscription sender

You can run the HL7 subscription sender directly with python or build docker image and run it in the container.
Destination host and port should be configured using environment variables configuration.

### Environment variables

- **LOG_LEVEL** - default 'INFO'
- **SERVICE_BUS_CONNECTION_STRING** - service bus connection string (optional, required when SERVICE_BUS_NAMESPACE is empty)
- **SERVICE_BUS_NAMESPACE** - service bus namespace (recommended, required when SERVICE_BUS_CONNECTION_STRING is empty)
- **INGRESS_SESSION_ID** - service bus queue FIFO session name (optional, sessions not used if not set)
- **RECEIVER_MLLP_HOST** - HL7/mllp destination server host
- **RECEIVER_MLLP_PORT** - HL7/mllp destination server port
- **ACK_TIMEOUT_SECONDS** - time for message acknowledgement
- **WORKFLOW_ID** - workflow id (used for audit)
- **MICROSERVICE_ID** - service id (used for audit)
- **HEALTH_CHECK_HOST** - default 127.0.0.1
- **HEALTH_CHECK_PORT** - default 9000
- **INGRESS_TOPIC_NAME** - service bus topic name under which a subscription is published
- **INGRESS_SUBSCRIPTION_NAME** - service bus subscription name to read subscription messages from

### Running directly

From the [hl7_subscription_sender](.) folder run:

```sh
python -m hl7_subscription_sender.application
```

### Running in docker

You can build the docker image with provided [Dockerfile](./Dockerfile) or you can run selected workflow
using Docker compose configuration in [local](../local/README.md).
