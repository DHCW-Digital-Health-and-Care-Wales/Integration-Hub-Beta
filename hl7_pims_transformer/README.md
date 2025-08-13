# HL7 PIMS Transformer

HL7 PIMS to MPI Transformer Service

### Dependencies

- [uv](https://docs.astral.sh/uv/) - Python package and project manager
- macOS: `brew install uv`
- Other platforms: See [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/)

### Build / checks

In the [hl7_pims_transformer](.) folder, to create a virtual environment and install project dependencies:

```bash
uv sync
```

Run code quality checks:

```bash
uv run ruff check
uv run bandit hl7_pims_transformer/**/*.py tests/**/*.py
uv run mypy --ignore-missing-imports hl7_pims_transformer/**/*.py tests/**/*.py
```

Run unit tests:

```bash
uv run python -m unittest discover tests
```

## Environment Variables

- **SERVICE_BUS_CONNECTION_STRING** - Service bus connection string (optional)
- **SERVICE_BUS_NAMESPACE** - Service bus namespace (optional)
- **INGRESS_QUEUE_NAME** - Queue to receive messages from (required)
- **EGRESS_QUEUE_NAME** - Queue to send transformed messages to (required)
- **AUDIT_QUEUE_NAME** - Audit logging queue (required)
- **WORKFLOW_ID** - Workflow identifier (required)
- **MICROSERVICE_ID** - Service identifier (required)
- **HEALTH_CHECK_HOST** - Health check hostname (optional, default: 127.0.0.1)
- **HEALTH_CHECK_PORT** - Health check port (optional, default: 9000)
- **LOG_LEVEL** - Logging level (optional, default: ERROR)

## Running

### Locally

```bash
python -m hl7_pims_transformer.application
```

### Docker

```bash
docker build -t hl7-pims-transformer .
docker run --env-file .env hl7-pims-transformer
```
