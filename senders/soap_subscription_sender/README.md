# SOAP Subscription Sender

Reads HL7 messages from an Azure Service Bus **topic subscription**, wraps each
message in a SOAP 1.1 envelope, and POSTs it to a configurable HTTP/SOAP endpoint.

Mirrors `hl7_subscription_sender` — MLLP transport replaced with HTTP/SOAP.

## Configuration

| Variable | Required | Description |
|---|---|---|
| `SERVICE_BUS_CONNECTION_STRING` | One of these | SAS connection string |
| `SERVICE_BUS_NAMESPACE` | One of these | Fully-qualified namespace (Managed Identity) |
| `INGRESS_TOPIC_NAME` | ✅ | Source topic |
| `INGRESS_SUBSCRIPTION_NAME` | ✅ | Subscription name |
| `INGRESS_SESSION_ID` | | Optional session filter |
| `SOAP_ENDPOINT_URL` | ✅ | Target SOAP endpoint |
| `SOAP_TIMEOUT_SECONDS` | | Default: 30 |
| `SOAP_API_KEY` | | ApiKey auth header (nullable) |
| `SOAP_CLIENT_CERT_PATH` | | Path to PEM client cert for mTLS (nullable) |
| `WS_SECURITY_ENABLED` | | `true` to enable WS-Security (reserved, default false) |
| `WORKFLOW_ID` | ✅ | Observability |
| `MICROSERVICE_ID` | ✅ | Observability |
| `HEALTH_BOARD` | ✅ | Observability |
| `PEER_SERVICE` | ✅ | Observability |
| `MAX_MESSAGES_PER_MINUTE` | | Throttle rate |
| `LOG_LEVEL` | | Default: `ERROR` |

## Running locally

```bash
uv sync
cp ../local/soap-subscription-sender.env .env
uv run python -m soap_subscription_sender.application
```

## Tests

```bash
uv run pytest
```
