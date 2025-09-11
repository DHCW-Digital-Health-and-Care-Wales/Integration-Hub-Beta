# HL7 Pharmacy Transformer

HL7 Pharmacy Transformer Service - validates MPI messages for Pharmacy system based on assigning authority.

## Features

- **Assigning Authority Validation**: Validates messages from MPI contain one of 12 specific assigning authorities required for Pharmacy
- **Message Processing**: Processes and forwards valid messages to Pharmacy systems
- **Error Handling**: Gracefully handles invalid assigning authorities and processing errors
- **Comprehensive Logging**: Logs assigning authority validation results and processing status

## Validation Details

### Valid Assigning Authorities

The transformer validates that messages contain one of the following assigning authorities in `PID.3.CX.4.HD.1`:

- 108, 109, 110, 111, 126, 131, 139, 140, 149, 170, 169, 310

### Validation Logic

Messages are validated using the XPath equivalent: `//ns1:PID/ns1:PID.3/ns1:CX.4/ns1:HD.1`

- **Valid**: Messages with matching assigning authority are processed and forwarded
- **Invalid**: Messages with non-matching or missing assigning authorities are rejected with error logging

## Development

### Dependencies

- [uv](https://docs.astral.sh/uv/) - Python package and project manager
- macOS: `brew install uv`
- Other platforms: See [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/)

### Build / checks

In the [hl7_pharmacy_transformer](.) folder, to create a virtual environment and install project dependencies:

```bash
uv sync
```

Run code quality checks:

```bash
uv run ruff check
uv run bandit hl7_pharmacy_transformer/**/*.py tests/**/*.py
uv run mypy --ignore-missing-imports hl7_pharmacy_transformer/**/*.py tests/**/*.py
```

Run unit tests:

```bash
uv run python -m unittest discover tests
```

## Environment Variables

- **SERVICE_BUS_CONNECTION_STRING** - Service bus connection string (optional)
- **SERVICE_BUS_NAMESPACE** - Service bus namespace (optional)
- **INGRESS_QUEUE_NAME** - Queue to receive messages from (required)
- **EGRESS_QUEUE_NAME** - Queue to send validated messages to (required)
- **AUDIT_QUEUE_NAME** - Audit logging queue (required)
- **WORKFLOW_ID** - Workflow identifier (required)
- **MICROSERVICE_ID** - Service identifier (required)
- **HEALTH_CHECK_HOST** - Health check hostname (optional, default: 127.0.0.1)
- **HEALTH_CHECK_PORT** - Health check port (optional, default: 9000)
- **LOG_LEVEL** - Logging level (optional, default: ERROR)

## Running

### Locally

```bash
python -m hl7_pharmacy_transformer.application
```

### Docker

```bash
docker build -t hl7-pharmacy-transformer .
docker run --env-file .env hl7-pharmacy-transformer
```

## Error Handling

The transformer handles the following error scenarios:

- **Invalid Assigning Authority**: Messages with non-matching assigning authorities are rejected
- **Missing PID Segment**: Messages without PID segments are rejected
- **Missing Fields**: Messages with missing required fields are rejected
- **Processing Errors**: Unexpected errors during message processing are logged and handled gracefully

All errors are logged with appropriate detail for troubleshooting and audit purposes.
