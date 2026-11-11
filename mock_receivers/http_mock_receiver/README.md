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
| `POST` | `/fhir/r4/$process-message` | Mock Promptly: accept a FHIR message Bundle, `202` + `Content-Location` |
| `GET` | `/fhir/r4/status/{id}` | Mock Promptly: `202` (`Retry-After`, `X-Progress`) until done, then `200` OperationOutcome |

## FHIR mock scenarios

The scenario is chosen by `Bundle.id` (state is in memory, lost on restart):

| `Bundle.id` | Behaviour |
|-------------|-----------|
| anything else | 202, two `202` polls, then `200` success |
| `mock-slow` | six `202` polls before success |
| `mock-error-outcome` | `200` with an `error` OperationOutcome |
| `mock-status-400` | status poll returns `400` |
| `mock-400` / `-401` / `-403` / `-404` / `-409` / `-429` / `-500` | POST rejected with that status (`429` adds `Retry-After`) |
| `mock-429-once` / `mock-500-once` | first POST for that id fails, the retry is accepted |

## Fault convention

If the request body contains the word `fail` (case-insensitive), the service returns
an HTTP 500 with a SOAP fault envelope — consistent with the `hl7_mock_receiver` NACK
convention.

## SOAP version support

- **SOAP 1.1** — `Content-Type: text/xml` (default)
- **SOAP 1.2** — `Content-Type: application/soap+xml` (detected automatically from namespace)

## Service Bus forwarding

Accepted (non-fault) requests are forwarded to `EGRESS_QUEUE_NAME` when Service Bus is
configured:

- **HL7 SOAP requests** (e.g. `<SendHL7Message><hl7Message>…`) — the extracted ER7 HL7
  payload is forwarded.
- **WIS SOAP requests** (the `CaptureFromFiorona` envelope used by the WIS SOAP sender,
  `SOAP_ENVELOPE_FORMAT=wis`) — the extracted `inputString` business payload is forwarded.
  If no `inputString` payload can be extracted, the complete raw SOAP envelope is
  forwarded instead.

Malformed (non-well-formed) XML is never forwarded to Service Bus.

- **FHIR Bundles** (`POST /fhir/r4/$process-message`) — the raw Bundle JSON is forwarded
  when the POST is accepted (`202`). Rejected POSTs (the `mock-4xx` / `mock-500` scenarios)
  are not forwarded, so a retried `*-once` scenario produces one queue message. This lets
  end-to-end tests confirm a message reached the end of the flow by reading `EGRESS_QUEUE_NAME`.

## Running locally

```bash
cd mock_receivers/http_mock_receiver
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
