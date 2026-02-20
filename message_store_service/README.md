# Message Store Service

Message storage service that reads HL7 messages from an Azure Service Bus queue and stores them in an Azure database for auditing and compliance purposes.

## Current Status

This is a skeleton implementation that currently:
- ✅ Reads messages from Azure Service Bus queue
- ✅ Logs received messages using EventLogger
- ⏳ TODO: Store messages in Azure Database (not yet implemented)

The service follows the same patterns as other Integration Hub services and is ready for database integration.

## Development

### Dependencies

- [uv](https://docs.astral.sh/uv/) - Python package and project manager
- macOS: `brew install uv`
- Other platforms: See [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/)

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

- **LOG_LEVEL** - default 'INFO'
- **SERVICE_BUS_CONNECTION_STRING** - service bus connection string (optional, required when SERVICE_BUS_NAMESPACE is empty)
- **SERVICE_BUS_NAMESPACE** - service bus namespace (recommended, required when SERVICE_BUS_CONNECTION_STRING is empty)
- **INGRESS_QUEUE_NAME** - service bus queue name to read messages from (required)
- **MICROSERVICE_ID** - service id used for audit logging (required)
- **HEALTH_CHECK_HOST** - default 127.0.0.1
- **HEALTH_CHECK_PORT** - default 9000

**Note:** This service does not use Service Bus sessions.

### Running directly

From the message_store_service folder run:

```sh
python -m message_store_service.application
```

### Running in docker

You can build the docker image with provided [Dockerfile](./Dockerfile) or you can run the service
using Docker compose configuration in [local](../local/README.md).
