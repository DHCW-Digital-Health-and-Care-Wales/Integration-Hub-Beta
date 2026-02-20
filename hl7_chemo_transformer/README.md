# HL7 Chemocare Transformer

HL7 Chemocare to MPI Transformer Service - transforms messages from Chemocare systems (SENDING_APP: 245, 212, 192, 224) to MPI format.

## Features

- **Conditional Processing**: Only processes messages from specific Chemocare SENDING_APP values
- **Field Mapping**: Implements comprehensive field mapping from Chemocare to MPI format
- **Hardcoded Values**: Adds required hardcoded values (ADT_A05, 2.5, NHS, NH, PI)
- **PID Restructuring**: Creates multiple PID.3 repetitions with NHS and Hospital formats
- **Robust Error Handling**: Gracefully handles missing fields and segments

## Transformation Details

### Processed SENDING_APP Values

- 245, 212, 192, 224

### Key Transformations

- **MSH.9/MSG.3** → Hardcoded "ADT_A05"
- **MSH.12/VID.1** → Hardcoded "2.5"
- **PID.3** → Restructured with NHS and Hospital identifier formats
- **PID.32** → Moved to PID.31

## Development

### Dependencies

- [uv](https://docs.astral.sh/uv/) - Python package and project manager
- macOS: `brew install uv`
- Other platforms: See [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/)

### Build / checks

In the [hl7_chemo_transformer](.) folder, to create a virtual environment and install project dependencies:

```bash
uv sync
```

Run code quality checks:

```bash
uv run ruff check
uv run bandit hl7_chemo_transformer/**/*.py tests/**/*.py
uv run mypy --ignore-missing-imports hl7_chemo_transformer/**/*.py tests/**/*.py
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
- **WORKFLOW_ID** - Workflow identifier (required)
- **MICROSERVICE_ID** - Service identifier (required)
- **HEALTH_CHECK_HOST** - Health check hostname (optional, default: 127.0.0.1)
- **HEALTH_CHECK_PORT** - Health check port (optional, default: 9000)
- **LOG_LEVEL** - Logging level (optional, default: ERROR)

## Running

### Locally

```bash
python -m hl7_chemo_transformer.application
```

### Docker

You can build the docker image with provided [Dockerfile](./Dockerfile) or you can run selected workflow
using Docker compose configuration in [local](../local/README.md).

```bash
docker build -t hl7-chemo-transformer .
docker run --env-file .env hl7-chemo-transformer
```
