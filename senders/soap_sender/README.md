# soap_sender

Queue-based SOAP/HTTP outbound sender for Integration Hub.

Reads HL7 ER7 messages from an Azure Service Bus session queue, wraps each message
in a SOAP 1.1 envelope, and POSTs it to a configured SOAP endpoint.  Mirrors
`hl7_sender` in structure — the only difference is the transport layer.

## How it fits in the flow

```
Service Bus queue (post-transform)
        ↓
  soap_sender  (Container App, no ingress, scale-to-zero)
        ↓  HTTP POST  (SOAP 1.1 envelope)
  SOAP endpoint
        ↓  HTTP response (SOAP ACK or fault)
  soap_sender  → Service Bus ACK or abandon
```

## Running locally

```bash
cd soap_sender
uv sync
# Start the http_mock_receiver first (via the Integration Hub Tester)
SOAP_ENDPOINT_URL=http://localhost:8080/soap \
INGRESS_QUEUE_NAME=... \
INGRESS_SESSION_ID=... \
MESSAGE_STORE_QUEUE_NAME=... \
WORKFLOW_ID=soap-sender \
MICROSERVICE_ID=soap-sender \
HEALTH_BOARD=... \
PEER_SERVICE=... \
uv run python -m soap_sender.application
```

## Environment variables

| Variable | Default | Required | Description |
|---|---|---|---|
| `SOAP_ENDPOINT_URL` | — | **Yes** | Full URL of the SOAP endpoint |
| `SOAP_TIMEOUT_SECONDS` | `30` | No | HTTP request timeout |
| `SOAP_API_KEY` | — | No | Added as `Authorization: ApiKey <key>` |
| `SOAP_CLIENT_CERT_PATH` | — | No | Path to PEM client cert for mTLS |
| `WS_SECURITY_ENABLED` | `false` | No | Reserved — WS-Security not yet implemented |
| `INGRESS_QUEUE_NAME` | — | **Yes** | Service Bus queue to consume from |
| `INGRESS_SESSION_ID` | — | **Yes** | Session ID for the ingress queue |
| `MESSAGE_STORE_QUEUE_NAME` | — | **Yes** | Message store queue name |
| `SERVICE_BUS_CONNECTION_STRING` | — | No | SB connection string (local/dev) |
| `SERVICE_BUS_NAMESPACE` | — | No | SB namespace (Managed Identity) |
| `WORKFLOW_ID` | — | **Yes** | Observability workflow identifier |
| `MICROSERVICE_ID` | — | **Yes** | Observability microservice identifier |
| `HEALTH_BOARD` | — | **Yes** | Health board identifier |
| `PEER_SERVICE` | — | **Yes** | Peer service name |
| `MAX_MESSAGES_PER_MINUTE` | — | No | Throttle rate |

## Running tests

```bash
uv run pytest
```

## Quality checks

```bash
bash check.sh
```
