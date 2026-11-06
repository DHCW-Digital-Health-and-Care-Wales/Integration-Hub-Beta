# fhir_sender

Queue-based outbound sender that delivers FHIR R4 message Bundles to Promptly using the
WPAS–Promptly IG `$process-message` operation (asynchronous pattern).

## How it fits in the flow

```
Service Bus queue (post-transform FHIR Bundle, e.g. from xml_fhir_proms_transformer)
        ↓
  fhir_sender
        ↓  POST [base]/$process-message   (application/fhir+json)
  Promptly  → 202 Accepted + Content-Location
        ↓  GET status URL (honours Retry-After) until 200 + OperationOutcome
  fhir_sender → Service Bus complete / abandon / dead-letter
```

## Outcome handling

| Result | Behaviour |
|---|---|
| `200` / `202` then `200` with a non-error OperationOutcome | Message completed |
| `400`, `404`, `409`, any other 4xx, or an `error`/`fatal` OperationOutcome | Not retried; OperationOutcome logged; message dead-lettered |
| `401` | OAuth2 mode: one retry with a fresh token; otherwise treated as `403` |
| `401` / `403` | `ALERT` logged, not retried; message abandoned (redrive after fixing credentials) |
| `429` | Retried after `Retry-After` (capped by `FHIR_MAX_RETRY_AFTER_SECONDS`) |
| `5xx`, network error, timeout | Exponential backoff up to `FHIR_MAX_ATTEMPTS`, then logged as failed and abandoned |
| Polling exceeds `FHIR_POLL_TIMEOUT_SECONDS` | Logged as failed and abandoned |
| Body is not a `Bundle` of `type=message` | Dead-lettered without a request |

Safeguards: HTTPS is required (plain HTTP only with `FHIR_ALLOW_INSECURE_HTTP=true`, for local mocks);
redirects are never followed; the status URL must be on the same host as the endpoint, because
credentials are sent to it.

Open IG questions (idempotency, 409 semantics, `traceId` exposure): the IG defines no idempotency
mechanism, so a retry after an unconfirmed POST or a polling timeout can resubmit a Bundle.

## Environment variables

| Variable | Default | Required | Description |
|---|---|---|---|
| `FHIR_ENDPOINT_URL` | — | **Yes** | Full `$process-message` URL, e.g. `https://wpas-fhir.stg.labs.promptly.health/fhir/r4/$process-message` |
| `FHIR_AUTH_MODE` | `api_key` | No | `api_key` or `oauth2` (one mechanism per environment) |
| `FHIR_API_KEY` | — | api_key mode | Sent as `X-API-Key` |
| `FHIR_OAUTH_TOKEN_URL` | — | oauth2 mode | e.g. `https://auth.promptly.health/oauth2/token` |
| `FHIR_OAUTH_CLIENT_ID` / `FHIR_OAUTH_CLIENT_SECRET` | — | oauth2 mode | Client credentials |
| `FHIR_OAUTH_SCOPE` | — | oauth2 mode | e.g. `target-entity:{entity_id}` |
| `FHIR_TIMEOUT_SECONDS` | `30` | No | Per-request timeout |
| `FHIR_MAX_ATTEMPTS` | `3` | No | Attempts per request for 429/5xx/network errors |
| `FHIR_BACKOFF_SECONDS` | `2` | No | Initial backoff (doubles each attempt) |
| `FHIR_MAX_RETRY_AFTER_SECONDS` | `60` | No | Cap on `Retry-After` waits |
| `FHIR_POLL_INTERVAL_SECONDS` | `5` | No | Poll delay when no `Retry-After` is given |
| `FHIR_POLL_TIMEOUT_SECONDS` | `120` | No | Maximum time to wait for processing to finish |
| `FHIR_ALLOW_INSECURE_HTTP` | `false` | No | Local development only |
| `INGRESS_QUEUE_NAME` | — | **Yes** | Service Bus queue to consume from |
| `INGRESS_SESSION_ID` | — | No | Session ID if the queue is session-enabled |
| `MAX_BATCH_SIZE` | `10` | No | Messages per receive; keep small because each may poll for up to the timeout |
| `SERVICE_BUS_CONNECTION_STRING` / `SERVICE_BUS_NAMESPACE` | — | One of | Local / Managed Identity |
| `WORKFLOW_ID`, `MICROSERVICE_ID`, `HEALTH_BOARD`, `PEER_SERVICE` | — | **Yes** | Observability identifiers |
| `HEALTH_CHECK_HOST`, `HEALTH_CHECK_PORT` | — | No | TCP health probe |

Credentials come from secure configuration only (never committed).

## Running tests and checks

```bash
uv run python -m unittest discover tests
bash check.sh
```
