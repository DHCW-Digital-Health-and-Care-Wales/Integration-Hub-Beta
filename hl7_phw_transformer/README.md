# HL7 PHW Transformer

PHW (Public Health Wales) message transformation service. Subscribes to PHW-specific messages (SENDING_APP: 252) to MPI format. Transforms relevant datetime fields to an MPI format.

## Transformation Details

This transformer converts PHW HL7 messages to MPI-compatible format through the following key transformations:

### DateTime Field Transformation (MSH-7)

- **From**: `YYYY-MM-DD HH:MM:SS` (e.g., `2023-01-15 09:45:30`)
- **To**: `YYYYMMDDHHMMSS` (e.g., `20230115094530`)
- **Applied to**: MSH.7 (Message creation timestamp)

Note that if the date is already in the deisred target format, no transformation will occur.

### Date of Death Handling (PID-29)

- **Special handling only**: The value `RESURREC` (case-insensitive) is transformed to `""` (empty string) to indicate resurrection/correction
- **All other values**: Passed through unchanged (only trimmed of whitespace)
- **Applied to**: PID.29 (Patient death date and time)

### Other Mappings

- **MSH segment**: Fields 3-21 are copied directly from source to target
- **PID segment**: Fields 1-28 and 30-39 are copied directly
- **Additional segments**: All other segments are copied without transformation

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
- **HEALTH_CHECK_PORT** - default 9000

### Running directly

From the hl7_phw_transformer folder run:

```sh
python -m hl7_phw_transformer.application
```

### Running in docker

You can build the docker image with provided [Dockerfile](./Dockerfile) or you can run selected workflow
using Docker compose configuration in [local](../local/README.md).
