# HL7 SOAP server

SOAP endpoint for receiving HL7v2 XML messages from authorised assigning authorities, validating against standard HL7 2.5 schemas, and forwarding valid payloads downstream over Service Bus.

## What it does

- Accepts SOAP 1.1 POST requests on a configurable endpoint path.
- Unwraps SOAP envelope and extracts a single HL7 business payload element.
- Validates payload against standard HL7 schemas from `shared_libs/hl7_validation` (for example `2_5_segments.xsd` via `ADT_A05.xsd` / `ADT_A39.xsd`).
- Applies business validation to ensure assigning authority is allowed (default: `328`).
- Converts valid HL7 XML payload to ER7 and forwards to configured Service Bus queue/topic.
- Returns SOAP success response for valid requests.
- Returns SOAP fault response for malformed SOAP, schema failures, and business rule failures.

## Development

### Dependencies

- [uv](https://docs.astral.sh/uv/)

### Install and run checks

From [hl7_soap_server](.) run:

```bash
uv sync
bash check.sh
```

### Run tests

```bash
uv run python -m unittest discover tests
```

## Running the server

### Key environment variables

- `HOST` (default `0.0.0.0`)
- `PORT` (default `8080`)
- `SOAP_ENDPOINT_PATH` (default `/soap`)
- `MAX_REQUEST_SIZE_BYTES` (default `1048576`)
- `HL7_SCHEMA_GROUP` (default `phw`)
- `ALLOWED_HL7_STRUCTURES` (default `ADT_A05,ADT_A39`)
- `ALLOWED_ASSIGNING_AUTHORITIES` (default `328`)
- `TLS_CERT_FILE` and `TLS_KEY_FILE` (optional; enable in-process HTTPS when both set)
- `SERVICE_BUS_CONNECTION_STRING` or `SERVICE_BUS_NAMESPACE`
- `EGRESS_QUEUE_NAME` or `EGRESS_TOPIC_NAME` (exactly one required)
- `EGRESS_SESSION_ID`
- `MESSAGE_STORE_QUEUE_NAME`
- `WORKFLOW_ID`
- `MICROSERVICE_ID`
- `HEALTH_BOARD`
- `PEER_SERVICE`
- `HEALTH_CHECK_HOST`
- `HEALTH_CHECK_PORT`

### Run locally

```bash
uv run python -m hl7_soap_server.application
```

### HTTPS note

Container Apps can terminate HTTPS at ingress. If required for local in-process TLS, set both `TLS_CERT_FILE` and `TLS_KEY_FILE`.
