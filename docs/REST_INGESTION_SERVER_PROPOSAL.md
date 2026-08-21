# Proposal: Configurable REST Ingestion Server

> Status: **Proposal** — no implementation yet. This document proposes generalising the existing
> `hl7_soap_server` into a **configurable, content-type-agnostic REST ingestion server**, built on
> the same shared-library foundation as `hl7_server`, so that multiple differently-configured
> instances can be deployed for different source systems and payload formats without new code per
> flow.

## Goal

Provide a single, reusable **HTTP/REST ingestion container** that can:

- Accept a POST payload over HTTP(S) — XML (SOAP-wrapped or plain), and in future JSON.
- Validate the payload against a **configurable schema** (XSD, JSON Schema, or a named business
  validator) selected entirely through environment variables — no code change per source system.
- Publish the validated payload to a configured Azure Service Bus queue/topic, using the **same
  downstream contract** as `hl7_server` (metadata properties, message store, event logging,
  metrics, FIFO session routing).
- Be deployed **more than once**, each instance configured for a different sending system,
  content type, schema and destination queue — the same "one image, many flows" model already used
  for `hl7_server` (PHW, Paris, Chemo, PIMS, WDS, Mosaiq, MPI outbound all run the same image with
  different env vars).

The key insight, carried over from the earlier SOAP spike: only the **transport, envelope and
validation rule-set** differ between source systems. Everything after "we have a validated payload
+ tracking metadata" should be **reused**, not re-implemented per flow.

## Current state

Two ingestion services exist today and both already follow the "shared core, config-driven flow"
pattern — this proposal extends that pattern rather than inventing a new one.

| Service | Transport | Payload | Validation | Reused today for |
|---|---|---|---|---|
| [`hl7_server`](../hl7_server/README.md) | MLLP/TCP | ER7 (pipe-delimited HL7v2) | `HL7Validator` + per-flow custom validation (`custom_validation/`) + optional flow XSD | PHW, Paris, Chemo, PIMS, WDS, Mosaiq, MPI outbound |
| [`hl7_soap_server`](../hl7_soap_server/README.md) | HTTP (SOAP 1.1 POST) | HL7 v2.xml, SOAP-enveloped | Hard-coded SOAP envelope unwrap + HL7 XSD (`HL7_SCHEMA_GROUP`) + assigning-authority allow-list | LIMS → MPI (`flow_lims_to_mpi.tf`) |

`hl7_soap_server` is the right starting point for this proposal — it already proves the REST/HTTP
ingestion model end-to-end (Service Bus publish, message store, event logging, metrics, health
check, in-process TLS) using the same shared libraries as `hl7_server`. However, it is **not yet a
generic REST server**: the SOAP envelope unwrap and the HL7-specific XSD/assigning-authority
validation are built directly into `SoapMessageProcessor`. Standing up a new instance for a
non-SOAP, non-HL7 source (e.g. a partner posting plain XML, or a FHIR-flavoured document) would
mean forking the service or hard-coding a second payload shape into it.

## Problem statement

We expect to onboard more than one HTTP-based source system, and they will not all look like SOAP
+ HL7 v2.xml:

- Some senders may POST **plain XML** with no SOAP envelope.
- Some payloads may need validation against a **different XSD per source**, not just an HL7
  structure/schema-group pair.
- Some sources may eventually send **JSON** rather than XML.
- Each source will have its own allow-list / business rule (today: assigning authority; tomorrow:
  API key, source system ID, structure allow-list, or nothing at all).

Without generalising the config surface, each new source becomes a new fork of `hl7_soap_server`
with duplicated transport/publish/logging code and its own drift risk — the same problem
`hl7_server` already solved for MLLP flows via `AppConfig` + pluggable validators.

## Proposed design

Generalise `hl7_soap_server` (rename to something transport-neutral, e.g. `rest_ingestion_server`,
or keep the existing package and add pluggable seams — see "Naming" below) around three pluggable
extension points, all selected by configuration:

```
                        ┌───────────────────────────────────────────────┐
  HTTP(S) POST ────────▶│  REST ingestion server (shared core)           │
                        │                                                │
                        │  1. Envelope adapter   (unwrap request body)   │
                        │  2. Validator          (schema / business rule)│
                        │  3. Output formatter   (payload sent onward)   │
                        │                                                │
                        │  ── shared, unchanged from hl7_server model ── │
                        │  event_logger_lib · metric_sender_lib          │
                        │  message_bus_lib (sender + message store)      │
                        │  health_check_lib · AppConfig pattern          │
                        └───────────────────┬───────────────────────────┘
                                            ▼
                              pre-*-transform queue/topic
```

### 1. Envelope adapter (`CONTENT_ADAPTER`)

Extracts the business payload from the raw HTTP body. Selected by env var; each value maps to a
small, already-largely-written function:

| `CONTENT_ADAPTER` | Behaviour | Existing code to reuse |
|---|---|---|
| `soap` | Unwrap `SOAP-ENV:Envelope`/`Body`, return the single child element | `_extract_soap_business_payload` in `hl7_soap_server/soap_processor.py` |
| `xml-raw` | Treat the whole body as the business payload (no envelope) | New — trivial, same `defusedxml` parse without the SOAP unwrap step |
| `json-raw` | Treat the whole body as JSON | New — `json.loads` with size guard |

### 2. Validator (`VALIDATOR_TYPE` + `VALIDATION_SCHEMA`)

| `VALIDATOR_TYPE` | Behaviour | Existing code to reuse |
|---|---|---|
| `hl7-xsd` | Resolve `VALIDATION_SCHEMA` (a schema-group/structure pair) via `hl7_validation.schemas.get_schema_xsd_path_for` and validate with `hl7_validation.validate_xml` | Already implemented in `soap_processor.py` |
| `xsd` | Validate the payload against an arbitrary XSD file path/mount (`VALIDATION_SCHEMA` = file path) | New — thin wrapper around the same `lxml`-based XSD validation already used by `hl7_validation` |
| `json-schema` | Validate JSON payload against a JSON Schema file | New — `jsonschema` package (small, well-maintained dependency) |
| `none` | Skip schema validation (still subject to size limits and well-formedness checks) | — |

A secondary, optional **business rule** hook mirrors `ALLOWED_ASSIGNING_AUTHORITIES` /
`ALLOWED_HL7_STRUCTURES` today: a generic `ALLOWED_SOURCE_IDENTIFIERS` + `SOURCE_IDENTIFIER_XPATH`
(or JSON path) pair, so allow-listing a sending system does not require new code — only config.

### 3. Output formatter (`OUTPUT_FORMAT`)

| `OUTPUT_FORMAT` | Behaviour |
|---|---|
| `er7` | Convert validated HL7 XML to ER7 before publishing (today's LIMS behaviour) — reuses `xml_to_er7` |
| `raw` | Publish the validated payload byte-for-byte (XML or JSON) — for non-HL7 content where downstream consumers expect the original document, not an HL7 wire format |

### Everything else stays as-is

Transport (`http.server` + optional in-process TLS), Service Bus publish, message store, event
logging, metrics, health check, and the `AppConfig.read_env_config()` pattern are already
transport/content agnostic in `hl7_soap_server` today and need **no change** — they should be lifted
unchanged into the generalised service.

## Configuration surface

Builds on the existing `hl7_soap_server` `AppConfig` (Service Bus, message store, workflow/audit,
health check, TLS all unchanged) plus:

| Variable | Purpose | Example |
|---|---|---|
| `ENDPOINT_PATH` | Generalises `SOAP_ENDPOINT_PATH` — request path this instance listens on | `/soap`, `/ingest/xml` |
| `CONTENT_ADAPTER` | Envelope unwrap strategy | `soap`, `xml-raw`, `json-raw` |
| `VALIDATOR_TYPE` | Validation strategy | `hl7-xsd`, `xsd`, `json-schema`, `none` |
| `VALIDATION_SCHEMA` | Schema selector — HL7 schema-group/structure pair, or a schema file path/mount | `phw`, `/schemas/partner-x.xsd` |
| `ALLOWED_SOURCE_IDENTIFIERS` | Generalises `ALLOWED_ASSIGNING_AUTHORITIES` — comma-separated allow-list | `328`, `partner-x` |
| `SOURCE_IDENTIFIER_LOCATOR` | Where to read the source identifier from the payload (XPath/JSON path) | `//MSH.3/HD.1` |
| `OUTPUT_FORMAT` | What gets published to Service Bus | `er7`, `raw` |
| `MAX_REQUEST_SIZE_BYTES` | Unchanged — reject oversized payloads before parsing | `1048576` |

Every other variable (`EGRESS_QUEUE_NAME`/`EGRESS_TOPIC_NAME`, `EGRESS_SESSION_ID`,
`MESSAGE_STORE_QUEUE_NAME`, `WORKFLOW_ID`, `MICROSERVICE_ID`, `HEALTH_BOARD`, `PEER_SERVICE`,
`HEALTH_CHECK_HOST/PORT`, `TLS_CERT_FILE`/`TLS_KEY_FILE`) is unchanged from `hl7_soap_server` /
`hl7_server` and should stay identically named for consistency across ingestion services.

Today's LIMS SOAP flow becomes just one configuration profile of the generalised server:
`CONTENT_ADAPTER=soap`, `VALIDATOR_TYPE=hl7-xsd`, `VALIDATION_SCHEMA=phw`, `OUTPUT_FORMAT=er7` — i.e.
**no behavioural change** for the existing flow, proving backward compatibility.

## Deployment model — "one image, many flows"

This mirrors the pattern already in production for `hl7_server` and already started for
`hl7_soap_server`/LIMS in `Integration-Hub-Terraform`:

- One container image, one `pyproject.toml`, one set of tests and quality gates.
- Each source system gets its **own Container App** (own name, own scaling, own ingress rule) built
  from the same image, differing only in environment variables — following the existing
  `container_apps_lims_to_mpi` block in
  [`components/app-platform/flow_lims_to_mpi.tf`](../../Integration-Hub-Terraform/components/app-platform/flow_lims_to_mpi.tf)
  as the template for new flows (`flow_<source>_to_mpi.tf`, its own `pre-*-transform` queue, its own
  `EGRESS_SESSION_ID`, its own alert thresholds).
- Onboarding a new REST source that fits an existing adapter/validator combination (e.g. another
  SOAP+HL7-XSD sender, or another plain-XML sender using a new XSD) requires **only** a new
  Terraform block and schema file — no code change and no new image to build/scan/release.
- Onboarding a genuinely new adapter or validator type (e.g. first JSON sender) requires one small,
  additive, well-tested code change to the shared server — not a fork.

## Proposed package layout

Evolve `hl7_soap_server` in place (or rename — see below) using the same "pluggable strategy"
convention `hl7_server` already uses for `custom_validation/`:

```
rest_ingestion_server/                  # or: hl7_soap_server, generalised in place
├── Dockerfile / pyproject.toml / uv.lock / check.sh / README.md   # unchanged conventions
└── rest_ingestion_server/
    ├── application.py                  # unchanged entry point (configure_otel + start_server)
    ├── app_config.py                   # extended per "Configuration surface" above
    ├── rest_server_application.py      # was hl7_soap_server_application.py — transport/lifecycle
    ├── message_processor.py            # was soap_processor.py — orchestrates the 3 pluggable steps
    ├── content_adapters/
    │   ├── soap_adapter.py             # existing SOAP unwrap logic, moved as-is
    │   ├── xml_raw_adapter.py          # new — no-envelope XML
    │   └── json_raw_adapter.py         # new — JSON body
    ├── validators/
    │   ├── hl7_xsd_validator.py        # existing HL7 schema-group validation, moved as-is
    │   ├── xsd_validator.py            # new — arbitrary XSD file
    │   └── json_schema_validator.py    # new — JSON Schema file
    ├── custom_message_properties.py    # unchanged
    └── wsdl_service.py                 # unchanged — only relevant when CONTENT_ADAPTER=soap
```

### Naming

Two options, worth a short discussion before implementation:

1. **Keep the `hl7_soap_server` name**, generalise its internals. Lowest churn (Terraform, ACR
   image names, pipelines unaffected), but the name becomes misleading once it also serves plain
   XML/JSON.
2. **Rename to `rest_ingestion_server`** (or similar), update Terraform image references. Clearer
   long-term, but touches deployed infrastructure and requires a coordinated release.

Recommendation: start with option 1 (generalise internals, keep the name and existing LIMS
deployment unchanged) and revisit the rename once a second, genuinely non-SOAP flow is live and the
old name is demonstrably wrong.

## Security considerations (NHS / clinical data)

These carry over unchanged from the original SOAP spike ([`SOAP_SERVER_SPIKE.md`](./SOAP_SERVER_SPIKE.md))
and apply to every deployed instance regardless of content type:

- **No application-level caller authentication by default.** TLS (in-container via
  `TLS_CERT_FILE`/`TLS_KEY_FILE`, or terminated at Container Apps ingress) proves the *server's*
  identity and encrypts transport — it does not authenticate the caller. Compensate at the network
  layer: private ingress/VNet, source-IP allow-listing, and NHS network/VPN transport. Call this out
  explicitly for information-governance sign-off per instance.
- **XXE / entity expansion (OWASP A05).** All XML parsing must go through `defusedxml` (already the
  case in `soap_processor.py`) with DTD loading and external entity resolution disabled — this
  applies to the new `xml-raw` adapter too, not just `soap`.
- **Oversized payloads / billion-laughs.** Enforce `MAX_REQUEST_SIZE_BYTES` before parsing, for
  every adapter, not just SOAP.
- **Schema as the trust boundary.** Every payload is untrusted until it passes the configured
  validator; `VALIDATOR_TYPE=none` should require an explicit, documented, per-instance justification
  since it removes that boundary.
- **JSON-specific:** guard against deeply nested/huge JSON documents (`json.loads` has no built-in
  depth limit) — cap nesting depth and payload size explicitly if/when `json-raw` is implemented.
- **No secrets in code or images.** Service Bus auth via Managed Identity; TLS key material and any
  future API keys via environment/Key Vault, never baked into the image, mirroring `ca-certs/`
  injection conventions.

## Testing approach

- Unit tests per pluggable component (`content_adapters/`, `validators/`) using `unittest`, mirroring
  the existing `tests/test_soap_processor.py` structure — one test module per adapter/validator so a
  new content type ships with its own coverage rather than inflating one large test file.
- Reuse the existing `hl7_soap_server` test suite unchanged as the regression baseline for the
  `soap` + `hl7-xsd` profile (today's LIMS behaviour) to prove no behavioural change.
- Add a config-validation test (`test_app_config.py`, already present) covering the new
  `CONTENT_ADAPTER`/`VALIDATOR_TYPE`/`OUTPUT_FORMAT` enums, including rejection of invalid/unknown
  values at startup rather than at first request.
- `check.sh` (ruff, bandit, mypy, pytest via `unittest`) unchanged.

## Phased delivery

1. **Phase 1 — refactor, no behaviour change.** Extract the existing SOAP unwrap and HL7-XSD
   validation into the `content_adapters`/`validators` structure above; introduce `AppConfig` fields
   with `soap`/`hl7-xsd`/`er7` as defaults so the current LIMS deployment is unaffected. Ship and
   verify against the existing LIMS flow before adding anything new.
2. **Phase 2 — add `xml-raw` + `xsd` validator.** Onboard the first non-SOAP XML source using purely
   additive code (new adapter/validator modules) and a new Terraform flow block.
3. **Phase 3 — add `json-raw` + `json-schema` validator** if/when a JSON-based source is confirmed.
   Only pursue this when there is a concrete source system requiring it.

## Open questions

- **Which concrete source system(s) drive Phase 2?** The design above is informed by the LIMS SOAP
  precedent; confirming the next real source (format, whether SOAP-wrapped, expected schema) will
  validate or adjust the adapter/validator list before implementation starts.
- **Where do per-instance schema files live?** Options: bundled in the image (simple, requires a
  rebuild per new schema), mounted via Container Apps secret/volume (no rebuild, more moving parts),
  or pulled from a shared schema store. `hl7_server`/`hl7_soap_server` currently bundle HL7 schemas
  from `shared_libs/hl7_validation`; a non-HL7 XSD/JSON Schema source needs an equivalent home.
- **Response contract per content type.** SOAP callers expect a SOAP success/fault envelope; a
  plain-XML or JSON sender may expect a simpler HTTP status + body contract. Confirm per source
  whether a generic `2xx`/`4xx` + short JSON/XML error body is acceptable, or whether each adapter
  needs its own response builder (mirroring `build_soap_success_response`/`build_soap_fault_response`).
  This must still respect the "ACK/success only after the Service Bus send completes" rule from
  `AGENTS.md`.
- **Transport library choice.** `hl7_soap_server` uses the stdlib `http.server`; `http_mock_receiver`
  uses FastAPI. Decide whether the generalised server stays on stdlib (fewer dependencies, matches
  today's implementation) or moves to FastAPI (richer request/response handling, easier to add new
  adapters/content-type negotiation) before Phase 1 lands.
