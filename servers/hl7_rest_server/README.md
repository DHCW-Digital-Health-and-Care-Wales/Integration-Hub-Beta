# hl7_rest_server

REST-based HL7 receiver for the NHS Wales Integration Hub. It accepts HL7 v2
messages over HTTP (ER7 or HL7 v2 XML), validates them, publishes them to Azure
Service Bus, persists a copy to the message store, and returns an HL7 ACK/NACK.

It is the HTTP counterpart to the MLLP-based [`hl7_server`](../hl7_server) and
reuses the same shared libraries (`message_bus_lib`, `hl7_validation`,
`event_logger_lib`, `metric_sender_lib`, `field_utils_lib`).

## API

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/hl7MessageReceiver` | Accept an HL7 message (`{"messageContent": "..."}`) and return an ACK/NACK |
| `GET`  | `/hl7MessageReceiver/ping` | Liveness probe |
| `GET`  | `/hl7MessageReceiver/status` | Readiness probe |
| `GET`  | `/docs` | Swagger UI (DEV/SIT only) |

### Responses

| Situation | Status | Body |
|-----------|--------|------|
| Message accepted | `201` | Raw HL7 ACK (`text/plain`, `MSA|AA|...`) |
| Validation failure | `422` | `{ "StatusCode": 422, "ErrorMessage": "<NACK>" }` |
| Malformed / missing body | `400` | `{ "StatusCode": 400, "ErrorMessage": "..." }` |
| Oversize message | `400` | `{ "StatusCode": 400, "ErrorMessage": "..." }` |
| Unparsable / internal error | `500` | `{ "StatusCode": 500, "ErrorMessage": "<generic NACK>" }` |

The Service Bus send happens synchronously inside the request handler; the `201`
ACK is only returned once the send completes successfully.

## Configuration

Configuration is read from environment variables (`hl7_rest_server/app_config.py`):

| Variable | Required | Description |
|----------|----------|-------------|
| `SERVICE_BUS_CONNECTION_STRING` | | Connection string (omit to use `SERVICE_BUS_NAMESPACE` + managed identity) |
| `SERVICE_BUS_NAMESPACE` | | Namespace for RBAC/managed-identity auth |
| `EGRESS_QUEUE_NAME` / `EGRESS_TOPIC_NAME` | one of | Destination queue **or** topic (mutually exclusive) |
| `EGRESS_SESSION_ID` | yes | Session id for the outbound message |
| `MESSAGE_STORE_QUEUE_NAME` | | Message store queue |
| `WORKFLOW_ID` | yes | Workflow identifier |
| `MICROSERVICE_ID` | yes | Microservice identifier |
| `HEALTH_BOARD` | yes | Health board code |
| `PEER_SERVICE` | yes | Downstream peer service name |
| `HL7_VERSION` | | Expected inbound HL7 version (validation) |
| `SENDING_APP` | | Expected inbound sending application (validation) |
| `HL7_VALIDATION_FLOW` | | Flow name for flow-schema validation (e.g. `mpi`, `risp`) |
| `HL7_VALIDATION_STANDARD` | | HL7 standard version for structural validation |
| `MAX_MESSAGE_SIZE_BYTES` | | Max accepted message size (default 1MB, cap 100MB) |
| `ENVIRONMENT` | | `DEV`/`SIT`/`TST`/... — gates Swagger UI |
| `HOST` / `PORT` | | Bind host/port (default `0.0.0.0:8080`) |
| `LOG_LEVEL` / `AZURE_LOG_LEVEL` | | Logging levels |

### RISP flow (`HL7_VALIDATION_FLOW=risp`)

RISP is a shared, multi-message-type source system that fans a single inbound message out to up
to two destinations (see the plan's §3a):

- `ADT^A28`/`ADT^A31`/`ADT^A40` (MSH.3 `349`) are forwarded as ER7 to `EGRESS_QUEUE_NAME`/`EGRESS_TOPIC_NAME`
  (the `risp-hl7-transformer` service), which delivers them on to MPI.
- `ADT^A40` is **additionally** converted to HL7 v2 XML and sent directly to WRRS.
- `ORU_R01`/`OMG_O19` (MSH.3 `350`-`358`) are validated against their custom XSD schema, converted
  to XML, and sent directly to WRRS only (not to the transformer/MPI).

When `HL7_VALIDATION_FLOW=risp`, the generic `SENDING_APP` check is skipped in favour of these
per-message-type MSH.3 rules, and the following additional variables are required:

| Variable | Required | Description |
|----------|----------|-------------|
| `WRRS_QUEUE_NAME` / `WRRS_TOPIC_NAME` | one of | WRRS destination queue **or** topic (mutually exclusive) |
| `WRRS_EGRESS_SESSION_ID` | yes | Session id for messages sent to WRRS |
| `WRRS_WORKFLOW_ID` | yes | Workflow identifier for messages sent to WRRS (e.g. `risp-to-wrrs`) |

## Local development

```bash
uv sync
uv run python -m hl7_rest_server.application
```

## Quality gate

```bash
bash check.sh
```

This runs `ruff` → `bandit` → `mypy` → `unittest`.

Run the tests directly with:

```bash
uv run python -m unittest discover tests
```

## Docker

```bash
docker build \
  --build-context ca-certs=../ca-certs \
  --build-context shared_libs=../shared_libs \
  -t hl7-rest-server .
```

The container runs as non-root (UID 5678) and exposes port `8080`.

