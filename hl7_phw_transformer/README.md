# HL7 PHW Transformer

PHW (Public Health Wales) message transformation service. Subscribes to PHW-specific messages (SENDING_APP: 252) to MPI format. Transforms relevant datetime fields to an MPI format.

## Development

### Dependencies

- [uv](https://docs.astral.sh/uv/) - Python package and project manager
- macOS: `brew install uv`
- Other platforms: See [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/)

### Build / checks

In the [hl7_phw_transformer](.) folder, to create a virtual environment and install project dependencies:

```bash
uv sync
```

Run code quality checks:

```bash
uv run ruff check
uv run bandit hl7_phw_transformer/**/*.py tests/**/*.py
uv run mypy --ignore-missing-imports hl7_phw_transformer/**/*.py tests/**/*.py
```

Run unit tests:

```bash
uv run python -m unittest discover tests
```

## Running HL7 PHW Transformer

You can run transformer directly with python or build docker image and run it in the container.

### Environment variables

- **LOG_LEVEL** - default 'INFO'
- **SERVICE_BUS_CONNECTION_STRING** - service bus connection string (optional, required when SERVICE_BUS_NAMESPACE is empty)
- **SERVICE_BUS_NAMESPACE** - service bus namespace (recommended, required when SERVICE_BUS_CONNECTION_STRING is empty)
- **EGRESS_QUEUE_NAME** - service bus queue name to store received messages
- **EGRESS_SESSION_ID** - service bus queue FIFO session name (optional, sessions not used if not set)
- **INGRESS_QUEUE_NAME** - service bus queue name to read messages from
- **INGRESS_SESSION_ID** - service bus queue FIFO session name (optional, sessions not used if not set)
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
