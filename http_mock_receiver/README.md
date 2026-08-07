# http_mock_receiver

HTTP/SOAP mock receiver for Integration Hub local testing.

Accepts inbound SOAP envelopes on `POST /soap`, logs the payload, and returns a
well-formed SOAP ACK or fault — mirroring the behaviour of `hl7_mock_receiver` for
the MLLP protocol.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/soap` | Accept a SOAP envelope, return ACK or fault |
| `GET` | `/health` | Liveness check — returns `200 OK` |

## Fault convention

If the request body contains the word `fail` (case-insensitive), the service returns
an HTTP 500 with a SOAP fault envelope — consistent with the `hl7_mock_receiver` NACK
convention.

## SOAP version support

- **SOAP 1.1** — `Content-Type: text/xml` (default)
- **SOAP 1.2** — `Content-Type: application/soap+xml` (detected automatically from namespace)

## Running locally

```bash
cd http_mock_receiver
uv sync
uv run python -m http_mock_receiver
# Server starts on http://0.0.0.0:8080
```

### Without Service Bus

The service runs in **log-only mode** when `EGRESS_QUEUE_NAME` is not set.  It still
accepts requests and returns valid SOAP responses — no Azure infrastructure required
for local testing.

## Environment variables

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `HOST` | `0.0.0.0` | No | Bind address |
| `PORT` | `8080` | No | Listen port |
| `LOG_LEVEL` | `INFO` | No | Python log level |
| `EGRESS_QUEUE_NAME` | — | No | Service Bus queue for forwarding |
| `EGRESS_SESSION_ID` | — | No | Session ID for the egress queue |
| `SERVICE_BUS_CONNECTION_STRING` | — | No | SB connection string (local emulator) |
| `SERVICE_BUS_NAMESPACE` | — | No | SB namespace (Managed Identity auth) |

## Running tests

```bash
uv run pytest
```

## Quality checks

```bash
bash check.sh
```
