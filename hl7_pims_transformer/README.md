# HL7 PIMS Transformer

PIMS message transformation service. Converts HL7 messages from PIMS systems (SENDING_APP: PIMS) to MPI-compatible HL7v2.5 format through comprehensive field mapping and message type transformations.

## Transformation Details

This transformer handles three PIMS message types (A04, A08, A40) and applies extensive transformations to ensure MPI compatibility:

### Message Type Conversion (MSH.9)

- **A04** → **A28** with structure **ADT_A05** (Add person information)
- **A08** → **A31** with structure **ADT_A05** (Update person information)
- **A40** → **A40** with structure **ADT_A39** (Merge patient)

### Hardcoded Values

- **MSH.3/HD.1, MSH.4/HD.1**: `103`
- **MSH.5/HD.1, MSH.6/HD.1**: `200`
- **MSH.9/MSG.1**: `ADT`
- **MSH.12/VID.1**: `2.5` (HL7 version)
- **MSH.17**: `GBR` (Country code)
- **MSH.19/CE.1**: `EN` (Principal language)

### DateTime Field Transformations

Timezone information is stripped from all timestamp fields:

- **MSH.7** (Message timestamp): Remove timezone (e.g., `20241231101053+0000` → `20241231101053`)
- **EVN.2, EVN.6**: Remove timezone from event timestamps
- **PID.7** (Date of birth): Remove timezone
- **PID.29** (Death date): Remove timezone or set to `""` if too short

### PID Segment Complex Mappings

- **PID.3 (Patient identifiers)**: Creates multiple repetitions with NHS number and hospital PI formats based on original values and message type
- **NHS number handling**: Special logic for N3/N4 prefixed NHS numbers in A04 messages
- **PID.5-8**: Name, birth date, sex copied with formatting preservation
- **PID.13**: Multiple phone number repetitions handled
- **PID.32**: Moved to PID.31 if present

### Segment-Specific Processing

- **EVN**: Event type and timestamps mapped with timezone removal
- **PD1**: General practitioner and primary care details (conditional based on message type)
- **PV1**: Patient visit information (conditional, mainly for A04/A08)
- **MRG**: Merge patient identifier (only for A40 messages)

## Development

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

You can build the docker image with provided [Dockerfile](./Dockerfile) or you can run selected workflow
using Docker compose configuration in [local](../local/README.md).

```bash
docker build -t hl7-pims-transformer .
docker run --env-file .env hl7-pims-transformer
```
