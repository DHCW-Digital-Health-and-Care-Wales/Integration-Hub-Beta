# Plan: Consolidate `hl7_rest_server` and `hl7_soap_server` into `rest_server`

## Goal

Retire both `hl7_rest_server` and `hl7_soap_server` as standalone services by folding their
behaviour into `rest_server`, so a single, configurable image can serve every REST/HTTP ingestion
flow (SOAP, plain XML, and HL7-over-JSON) and it's exclusively `rest_server` that gets deployed
and maintained going forward. The merged capability must remain **configuration-driven**
(environment variables only, per instance) — no code branching per flow, matching `rest_server`'s
existing design philosophy.

`hl7_soap_server` is the smaller piece of this: `rest_server`'s existing `CONTENT_ADAPTER=soap` +
`VALIDATOR_TYPE=hl7-xsd` combination already reproduces its behaviour almost exactly (see
[§9](#9-consolidating-hl7_soap_server) below), so it needs parity verification and a Terraform
cutover rather than new code. `hl7_rest_server` is the larger piece and needs the new `hl7`
pipeline described below. `hl7_server` (MLLP/TCP) is explicitly **out of scope** — it's a
different transport model and doesn't belong in an ASGI/HTTP server.

## Why this isn't a drop-in copy

`rest_server` was built around one shape of ingestion: unwrap an envelope → validate an XML
payload → optionally format it → publish to **one** destination → build a response with the same
adapter that did the unwrap. `hl7_rest_server` doesn't fit that shape in several ways:

| Aspect | `rest_server` (today) | `hl7_rest_server` |
|---|---|---|
| Request body | Raw XML / SOAP envelope | JSON `{"messageContent": "..."}`, ER7 **or** HL7 v2 XML |
| Native payload form | XML string throughout | Parsed `hl7apy.core.Message` (ER7 is primary; XML is only for message-store/WRRS) |
| Response | Adapter-built XML/SOAP ack or fault, keyed only by `message_control_id` | Raw HL7 ACK/NACK string built from **MSH fields of the parsed message** (`MSH.3/4/10/12`), with distinct HTTP codes (201/400/422/500) |
| Validation | Single `Validator.validate(xml, structure_id)` step | Multi-stage: common `HL7Validator` (version/sending app) → optional flow-schema XML validation → optional standard validation → flow-specific custom validation (MPI, RISP) |
| Destinations | Exactly one sender client | RISP flow fans a single inbound message out to **up to two** destinations (`mpi_transformer`, `wrrs`) in different formats (ER7 vs XML) |
| Extra routes | `/health` only | `/hl7MessageReceiver/ping`, `/hl7MessageReceiver/status` (with response-time/health-state tracking) |
| Docs gating | Always on | Swagger/OpenAPI only exposed in `DEV`/`SIT` (`ENVIRONMENT` env var) |
| Per-flow message properties | None | `FLOW_PROPERTY_BUILDERS` (e.g. MPI-specific Service Bus properties) |

Trying to force HL7-JSON through the existing `ContentAdapter`/`Validator`/single-destination
pipeline would mean bolting parsed-message state and multi-destination fan-out onto interfaces
that were deliberately kept simple for the SOAP/XML-raw case, degrading both. Instead, this plan
generalises `rest_server` one level up: **the whole request→response pipeline becomes the
pluggable unit** (a "profile"), while the infrastructure wiring underneath it (Service Bus,
message store, event logging, metrics, health check) is shared.

## Proposed design

### 1. Introduce a `PIPELINE` config switch

Add `PIPELINE` (`generic` | `hl7`, default `generic`) to `rest_server/app_config.py`.

- `PIPELINE=generic` — today's behaviour, unchanged: `CONTENT_ADAPTER` (`soap`/`xml-raw`),
  `VALIDATOR_TYPE` (`hl7-xsd`/`xsd`/`none`), `OUTPUT_FORMAT` (`er7`/`raw`), single
  `EGRESS_QUEUE_NAME`/`EGRESS_TOPIC_NAME` destination, `/health` route.
- `PIPELINE=hl7` — new, ported from `hl7_rest_server`: JSON `messageContent` body, HL7
  ACK/NACK responses, flow-based validation, optional RISP multi-destination routing,
  `/hl7MessageReceiver/*` routes, Swagger gating.

`CONTENT_ADAPTER`/`VALIDATOR_TYPE`/`OUTPUT_FORMAT` are only required/validated when
`PIPELINE=generic`; the HL7-specific variables below are only required/validated when
`PIPELINE=hl7` — mirroring the existing pattern where `WRRS_*` variables are only validated
when `HL7_VALIDATION_FLOW=risp`.

### 2. Extract shared infrastructure wiring

`rest_server_application.py` and `hl7_rest_server/runtime.py` currently duplicate the same
Service Bus/message-store/event-logger/metric-sender/health-check wiring. Factor this into a
new `rest_server/infra.py`:

```python
@dataclass
class SharedResources:
    sender_client: MessageSenderClient
    message_store_client: MessageStoreClient
    event_logger: EventLogger
    metric_sender: MetricSender
    health_check_server: TCPHealthCheckServer | None

def build_shared_resources(config: CommonConfig) -> SharedResources: ...
def build_extra_sender_client(config: CommonConfig, queue: str | None, topic: str | None, session_id: str) -> MessageSenderClient: ...
```

Both pipelines call into this module instead of re-implementing client construction/teardown.

### 3. Add the HL7 pipeline as a new subpackage

Create `rest_server/hl7/` and port the following modules from `hl7_rest_server`, adjusted to
import shared infra/config from `rest_server` instead of duplicating:

- `models.py` — `HL7Message` pydantic request model.
- `api_constant.py` — ACK/NACK wire-format constants.
- `hl7_ack_builder.py` — `HL7AckBuilder` (unchanged logic).
- `hl7_validator.py` — `HL7Validator` (version/sending-app/flow checks).
- `message_input_adapter.py` — `to_er7()` (ER7/XML detection + normalisation).
- `hl7_message_processor.py` — `Hl7MessageProcessor` (the transport-agnostic pipeline: parse →
  validate → flow-schema validate → standard-validate → store → send → ACK).
- `risp_routing.py` + `custom_validation/` + `exceptions/` — RISP multi-destination routing and
  flow-specific validation (MPI, RISP), unchanged.
- `custom_message_properties.py` — merge with `rest_server`'s existing (simpler) version; keep
  `FLOW_PROPERTY_BUILDERS` since `rest_server`'s generic pipeline has no equivalent need today.
- `routes/health.py`, `routes/messages.py` — ping/status/message routes, adjusted to read from
  the new runtime context.
- `errors.py` — `Hl7ParseError`/`Hl7ValidationError` (distinct from `rest_server.errors`, which
  stays used by the generic pipeline only).

### 4. Config additions (`rest_server/app_config.py`)

New fields, all optional unless `PIPELINE=hl7`:

| Variable | Required when | Description |
|---|---|---|
| `PIPELINE` | always | `generic` (default) or `hl7` |
| `HL7_VERSION` | | Expected inbound HL7 version |
| `SENDING_APP` | | Expected inbound sending application (comma-separated allow-list) |
| `HL7_VALIDATION_FLOW` | | `mpi`, `risp`, or unset |
| `HL7_VALIDATION_STANDARD` | | HL7 standard version for structural validation |
| `WRRS_QUEUE_NAME` / `WRRS_TOPIC_NAME` | `HL7_VALIDATION_FLOW=risp` | WRRS destination |
| `WRRS_EGRESS_SESSION_ID` | `HL7_VALIDATION_FLOW=risp` | Session id for WRRS messages |
| `WRRS_WORKFLOW_ID` | `HL7_VALIDATION_FLOW=risp` | Workflow id for WRRS messages |
| `ENVIRONMENT` | | Reused as-is to gate Swagger (`DEV`/`SIT`) for the `hl7` pipeline; generic pipeline keeps docs always-on |

`EGRESS_QUEUE_NAME`/`EGRESS_TOPIC_NAME`, `EGRESS_SESSION_ID`, `MESSAGE_STORE_QUEUE_NAME`,
`WORKFLOW_ID`, `MICROSERVICE_ID`, `HEALTH_BOARD`, `PEER_SERVICE`, `HOST`/`PORT` are already
common to both servers and need no changes.

**`MAX_REQUEST_SIZE_BYTES` stays a single variable, shared by both pipelines** —
`hl7_rest_server`'s separate `MAX_MESSAGE_SIZE_BYTES` is dropped, not aliased. Both pipelines
currently treat any configured value `<= 0` as "use the 1MB default", which silently discards a
deliberate attempt to raise the limit. Replace that with an explicit sentinel:

- Unset / `0` → default to 1MB, as today.
- A positive value up to the Azure Service Bus Premium ceiling (100MB) → used as configured, as
  today.
- `-1` → **no explicit cap below the Service Bus ceiling**: the request-size guard enforces the
  100MB Service Bus limit instead of the 1MB default, rather than being truly unbounded. Even an
  explicit "no limit" configuration must not allow unbounded request bodies (OWASP A05 — DoS via
  resource exhaustion), so the absolute ceiling is never removable, only the smaller default.
- Any other negative value, or a value above the Service Bus ceiling → configuration error at
  startup (unchanged).

### 5. Dispatch in `rest_server_application.py`

`RestServerApplication.build_app()` becomes a thin dispatcher:

```python
def build_app(self) -> FastAPI:
    config = AppConfig.read_env_config()
    if config.pipeline == "hl7":
        return self._build_hl7_app(config)
    return self._build_generic_app(config)  # today's build_app(), renamed
```

Each `_build_*_app` wires its own processor/router/lifespan via shared infra from `infra.py`.

### 6. Dependency updates

`rest_server/pyproject.toml` already carries `hl7apy` and `hl7_validation_lib`; add
`field-utils-lib` (used by `HL7Validator`, `hl7_ack_builder`, `custom_message_properties`) as a
local `uv.sources` path dependency, matching the pattern used for the other shared libs.

### 7. Tests

Port `hl7_rest_server/tests/*` into `rest_server/tests/hl7/` (adjusting imports), so the merged
`rest_server` test suite covers both pipelines. Add a small set of "pipeline selection" tests in
`test_app_config.py`/`test_rest_server_application.py` confirming:

- `PIPELINE=generic` (default) behaves exactly as today (no regression).
- `PIPELINE=hl7` requires the HL7-specific variables and **fails fast** (`RuntimeError` at
  startup, before any Service Bus connection is attempted) if `CONTENT_ADAPTER`, `VALIDATOR_TYPE`,
  or `OUTPUT_FORMAT` are also set — these belong to the generic pipeline only and setting them
  alongside `PIPELINE=hl7` is a misconfiguration, not a no-op.
- `HL7_VALIDATION_FLOW=risp` still requires `WRRS_*` only in the `hl7` pipeline.
- `MAX_REQUEST_SIZE_BYTES=-1` enforces the Service Bus 100MB ceiling instead of the 1MB default,
  in both pipelines.

### 8. Decommissioning `hl7_rest_server`

Once `rest_server` has full parity (verified by the ported tests plus a manual smoke test of each
flow currently served by `hl7_rest_server` — PHW, MPI outbound, RISP):

1. Update `Integration-Hub-Terraform` container app definitions/tfvars that currently deploy
   `hl7_rest_server` to instead deploy `rest_server` with `PIPELINE=hl7` and the appropriate
   flow-specific env vars.
2. Update `pipeline-ado/` build/deploy stages to stop building/pushing the `hl7_rest_server`
   image.
3. Remove the `hl7_rest_server/` directory, its `Dockerfile`, and any dedicated pipeline
   references, once at least one full environment cycle (DEV → TST → UAT) has run on `rest_server`
   without incident.

This step touches production NHS Wales infrastructure and must go through the normal
plan-review-approve pipeline gates in `Integration-Hub-Terraform` — no direct `terraform apply`.

## 9. Consolidating `hl7_soap_server`

Unlike `hl7_rest_server`, this doesn't need a new pipeline — `rest_server`'s existing `generic`
pipeline (`CONTENT_ADAPTER=soap`, `VALIDATOR_TYPE=hl7-xsd`) already implements the same envelope
unwrap and HL7-XSD validation as `hl7_soap_server`'s `SoapMessageProcessor`. The work here is
parity verification and cutover, not development, but two default-value gaps must be closed
first or the LIMS→MPI flow's behaviour will silently change on cutover:

| Setting | `hl7_soap_server` default | `rest_server` (`generic`) default | Action needed |
|---|---|---|---|
| Assigning-authority allow-list | `ALLOWED_ASSIGNING_AUTHORITIES` defaults to `328` (always enforced) | `ALLOWED_SOURCE_IDENTIFIERS` defaults to empty (no enforcement) | Terraform must set `ALLOWED_SOURCE_IDENTIFIERS=328` explicitly for the LIMS→MPI instance — do not rely on the default |
| HL7 schema group | `HL7_SCHEMA_GROUP` defaults to `phw` | `VALIDATION_SCHEMA` has no default (required) | Terraform must set `VALIDATION_SCHEMA=phw` explicitly |
| Endpoint path | `SOAP_ENDPOINT_PATH` defaults to `/soap` | `ENDPOINT_PATH` defaults to `/ingest` | Terraform must set `ENDPOINT_PATH=/soap` to avoid a URL change for the existing LIMS caller |

Also confirm the SOAP success/fault response body produced by `rest_server`'s `SoapContentAdapter`
is byte-for-byte acceptable to the LIMS caller (it is a simplified `AckResponse`/`Fault` shape, not
a copy of `hl7_soap_server`'s exact WSDL-derived response) — treat any difference as a breaking
change requiring caller sign-off, not a cosmetic one.

### Characterization test findings

Steps 1 and the fix noted in step 2 (below) are done —
[`rest_server/tests/test_hl7_soap_server_parity.py`](../rest_server/tests/test_hl7_soap_server_parity.py)
exercises `rest_server`'s `generic` pipeline (configured as in the table above) with the same
sample LIMS payloads as `hl7_soap_server/tests/test_soap_processor.py`. The core cases (valid,
malformed SOAP, schema-invalid, unauthorised assigning authority) match `hl7_soap_server`'s status
codes and fault text. Two genuine behavioural gaps were found and have since been fixed:

| Gap | `hl7_soap_server` | `rest_server` (`generic`) — now fixed |
|---|---|---|
| Payload with no extractable assigning authority (no HD.1 in MSH.3/MSH.4/PID.3) | `400 Client.Validation`, "Unable to determine assigning authority from payload." — raised eagerly during extraction | `SoapContentAdapter.extract()` now raises the same `400 Client.Validation` fault immediately, instead of returning `source_identifier=None` and letting the allow-list check misreport it as `403` |
| Structure allowed (`ALLOWED_HL7_STRUCTURES`) but missing from the configured schema group's XSD mapping (deployment misconfiguration) | `500 Server.Configuration`, "SOAP schema mapping is not configured." | `Hl7XsdValidator` now raises a distinct `500 Server.Configuration` `RequestError` instead of the generic `400 Client.Validation` `ValidationError` used for real payload failures |

Both fixes are covered by regression tests in `test_hl7_soap_server_parity.py`,
`tests/test_content_adapters.py` and `tests/test_validators.py`.

Steps:

1. ✅ Characterization tests comparing `hl7_soap_server` and `rest_server` (`generic`, configured
   as above) responses for the same set of sample LIMS payloads (valid, schema-invalid,
   unauthorised assigning authority, malformed SOAP) — see findings above.
2. ✅ Fix the two gaps found above. Remaining: update the LIMS→MPI Terraform flow module to
   deploy `rest_server` with the explicit config above instead of `hl7_soap_server`, staged
   DEV → TST → UAT as usual.
3. Remove `hl7_soap_server/`, its `Dockerfile`, and pipeline references once the flow has run
   without incident through at least one full environment cycle.

## Decisions

- **Fail fast on cross-pipeline misconfiguration.** Setting `CONTENT_ADAPTER`, `VALIDATOR_TYPE`,
  or `OUTPUT_FORMAT` while `PIPELINE=hl7` is a startup error, not a silently-ignored no-op.
- **One size-limit variable.** `MAX_REQUEST_SIZE_BYTES` is shared by both pipelines;
  `MAX_MESSAGE_SIZE_BYTES` is retired rather than kept as an alias. `-1` is a supported sentinel
  meaning "enforce the Service Bus 100MB ceiling instead of the 1MB default" (see §4).
- **`hl7_soap_server` is in scope too.** It's consolidated via the existing `generic` pipeline
  (no new pipeline needed) — see §9.

## Suggested implementation order

1. `infra.py` extraction (shared resource wiring) — no behaviour change, generic pipeline only.
2. Add `PIPELINE` config + dispatcher (with fail-fast cross-pipeline validation) and the
   `MAX_REQUEST_SIZE_BYTES=-1` sentinel; generic pipeline still the only implementation.
3. Port the `hl7/` subpackage and wire `PIPELINE=hl7` end-to-end.
4. Port tests; run both pipelines' suites together via `check.sh`.
5. Update `README.md` (`rest_server`) to document the `hl7` pipeline alongside the generic one.
6. Terraform/pipeline cutover and `hl7_rest_server` removal (separate PRs, staged per environment).
7. `hl7_soap_server` parity verification (§9) and Terraform cutover (separate PR(s), staged per
   environment) — can happen in parallel with steps 3-6 since it depends only on the `generic`
   pipeline, which is unchanged by this work.
