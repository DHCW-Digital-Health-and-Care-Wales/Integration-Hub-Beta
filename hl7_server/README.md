# HL7 MLLP server

Configurable HL7 MLLP server built with hl7apy package.

## Development

### Dependencies

- [uv](https://docs.astral.sh/uv/) - Python package and project manager
- macOS: `brew install uv`
- Other platforms: See [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/)

### Build / checks

In the [hl7_server](.) folder, to create a virtual environment and install project dependencies:

```bash
uv sync
```

Run code quality checks:

```bash
uv run ruff check
uv run bandit hl7_server/**/*.py tests/**/*.py
uv run mypy --ignore-missing-imports hl7_server/**/*.py tests/**/*.py
```

Run unit tests:

```bash
uv run python -m unittest discover tests
```

## Running HL7 server

You can run the HL7 server directly with python or build docker image and run it in the container.
To define host and port the server should bind to use environment variables configuration.

### Environment variables

- **HOST** - default 127.0.0.1
- **PORT** - default 2575
- **LOG_LEVEL** - default 'INFO'
- **SERVICE_BUS_CONNECTION_STRING** - service bus connection string (optional, required when SERVICE_BUS_NAMESPACE is empty)
- **SERVICE_BUS_NAMESPACE** - service bus namespace (recommended, required when SERVICE_BUS_CONNECTION_STRING is empty)
- **EGRESS_QUEUE_NAME** - service bus queue name to store received messages
- **AUDIT_QUEUE_NAME** - service bus queue name for storing audit events
- **WORKFLOW_ID** - workflow id (used for audit)
- **MICROSERVICE_ID** - service id (used for audit)
- **HL7_VERSION** - hl7v2 version, if provided will be used to validate MSH-12.1 field
- **SENDING_APP** - sending application id, optional, if provided will be used to validate MSH-3.1 field
- **HEALTH_CHECK_HOST** - default 127.0.0.1
- **health_check_port** - default 9000

### Running directly

From the [hl7_server](.) folder run:
```sh
python -m hl7_server.application
```

### Running in docker

You can build the docker image with provided [Dockerfile](./Dockerfile) or you can run selected workflow
using Docker compose configuration in [local](../local/README.md).
