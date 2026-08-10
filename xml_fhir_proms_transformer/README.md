# proms_fhir_transformer

Queue-driven transformer converting **WPAS XML** into a **FHIR R4B message Bundle**
for **PROMS** (PSOM — Patient Standard Outcome Measures).

> **Naming note:** the directory and the `PromsFhirTransformer` class name date from
> an earlier assumption that the source was HL7v2-XML. The confirmed source format
> is a bespoke WPAS XML schema, so a rename to `proms_fhir_transformer` /
> `PromsFhirTransformer` is pending agreement.

## Source of truth

All mappings are derived from the INSE Azure DevOps wiki, which documents the
**production Fiorano `WPAS_To_PROMS` workflow this service replaces**:

- `Integration Services/Software Design Documents/PROMS/WPAS_To_PROMS` — workflow design
- `.../WPAS_To_PROMS/Mapping Tables` — the field-by-field mapping (**authoritative**)
- `.../WPAS_To_PROMS/Javascript Functions` — the three lookup functions
- `.../WPAS_To_PROMS/Routing Rules` — `ROUTING_RULES_WPAS`

The earlier `Proms Mappings.xlsx` / `PROMS Scenarios.xlsx` spreadsheets describe a
materially different model (eight `eventCode` scenarios, `ServiceRequest`/
`Procedure`/`Appointment`/`Encounter`, Promptly Health profiles, FHIR R5). Where
the two disagree the **wiki wins**, by decision of the specification owner.

## What this is

- Ingests a bespoke WPAS XML payload (**not** HL7v2-XML). None of the HL7 tooling
  used by the other transformers (`hl7_validation.xml_to_er7`, `hl7apy`,
  `field_utils_lib`) applies here.
- Routes on the WPAS message type — `OPI`, `RFI` or `MPA` — taken from an explicit
  `MESSAGE_TYPE` field or, failing that, the XML root element.
- Builds a FHIR **R4B** `Bundle` with `type = "message"` and a `MessageHeader` at
  `entry[0]`. Entry order is **positional and normative** — the mapping tables
  address entries by index.
- Every resource carries a `meta.profile` from the Data Standards Wales PSOM
  profile set and a UUID id, cross-referenced between entries via `urn:uuid:`
  `fullUrl` values.
- Emits the Bundle as FHIR JSON to the egress queue.
- Mirrors the folder/module layout of `hl7_pims_transformer` (mappers/, tests/,
  Dockerfile, pyproject.toml, check.sh) for consistency with the rest of the repo.

## Message type routing

`message_types.py` encodes the whole routing table; `resolve_message_type()` is the
single decision point.

| `MESSAGE_TYPE` | Name | `MessageHeader.eventCoding` | Bundle entries |
|---|---|---|---|
| `OPI` | Outpatient | `psom-request` | `MessageHeader`, `CarePlan`, `Task` (EQ5D5L), `Task` (DataEntry), `Patient`, `Practitioner`, `Organization` |
| `RFI` | Referral | `psom-request` | *as `OPI`* |
| `MPA` | PatientUpdate | `patient-update` | `MessageHeader`, `Patient` |

`OPI` and `RFI` differ in exactly two places: the WPAS field holding the
practitioner's GMC number (`CONS_GMC` vs `REFERRING_GP`) and the field behind
`MessageHeader.responsible.display` (`CONS_NAME` vs `REFERRING_GP`).

`MPR` is routed to this queue by `ROUTING_RULES_WPAS` but the mapping tables define
no transform for it, so it is **explicitly rejected** rather than silently treated
as a patient update. Unroutable messages likewise raise `ValueError`, so
`process_message` records a transformation failure rather than emitting an
incorrect bundle.

## WPAS source fields

`SYSTEM_ID`, `DHA_CODE`, `UNIQUE_ID`, `NHS_NUMBER`, `NHS_CERTIFICATION`,
`UNIT_NUMBER`, `SURNAME`, `FORENAME`, `SEX`, `BIRTHDATE`, `POSTCODE`, `DEATHDATE`,
`PREFERRED_LANGUAGE`, `SPEC`, `SPEC_NAME`, `CONS_NAME`, `CONS_GMC`, `REFERRING_GP`,
`UPI_EVENT`, `UPI_EVENT_DESC`, `UPI_EVENT_DATE`.

`proms_parser.normalise_key()` lower-cases and strips separators, so a single
lookup tolerates dialect variation (`NHS_NUMBER` ≡ `nhsNumber` ≡ `nhs-number`).
Leaf elements are indexed regardless of nesting depth and namespace prefixes are
stripped, so changes to the payload's element hierarchy do not require parser
changes.

XML is parsed with `defusedxml`, matching the convention in
`shared_libs/hl7_validation`.

## Lookups ported from the wiki

`reference_data.py` and `source_systems.py` port the wiki's three JavaScript
functions verbatim, including their behaviour of **returning the input unchanged**
when a code is unrecognised:

| Function | Purpose |
|---|---|
| `nhs_certification_display()` | `NHS_CERTIFICATION` `01`–`08` -> NHS number verification status text |
| `dha_code_name()` | `DHA_CODE` `7A1`/`7A2`/`7A3`/`7A5`/`7A6`/`7A7` -> health board name (note: no `7A4`) |
| `get_pas_identifier_system()` | `SYSTEM_ID` -> the health board's PAS identifier URL |

## The Core Reference Data gap

The Fiorano flow calls an external `CoreReferenceDataLookup_Service` (SOAP) to
resolve `SEX` and `PREFERRED_LANGUAGE`. **No equivalent capability exists anywhere
in the Integration Hub.**

This is modelled as a `ReferenceDataResolver` Protocol so the seam is explicit and
replaceable. The shipped `StaticReferenceDataResolver`:

- maps `SEX` to a FHIR `administrative-gender` code locally, and
- **always returns `None` for language**, so `Patient.communication` is omitted
  rather than guessed.

A real resolver can be injected without touching any mapper:

```python
PromsFhirTransformer(resolver=MyLookupServiceResolver())
build_fhir_bundle(message, resolver=MyLookupServiceResolver())
```

## How it plugs into the shared processing loop

`transformer_base_lib` exposes two wire-format hooks on `BaseTransformer`, which
default to the standard HL7-in/HL7-out behaviour. This service overrides both:

| Hook | Default (other transformers) | This transformer |
|---|---|---|
| `parse_input(body)` | `parse_message(body)` (ER7) | `parse_proms_xml(body)` -> `PromsMessage` |
| `transform_message(msg)` | `Message` -> `Message` | `PromsMessage` -> FHIR `Bundle` |
| `serialise_output(result)` | `result.to_er7()` | `result.model_dump_json()` |

Everything else — Service Bus connectivity, health checks, audit logging,
batching — is inherited unchanged from `BaseTransformer.run()`. The hooks are
additive and default to the previous behaviour, so `hl7_phw_transformer`,
`hl7_chemo_transformer` and `hl7_pims_transformer` are unaffected.

A standalone convenience entry point is also available for ad-hoc use and testing:

```python
from proms_fhir_transformer.proms_transformer import transform_proms_xml_to_fhir_bundle

bundle = transform_proms_xml_to_fhir_bundle(wpas_xml_message)
print(bundle.model_dump_json(indent=2))
```

`build_fhir_bundle()` accepts an injectable `uuid_factory`, which the tests use to
produce deterministic bundles.

## Module layout

| Module | Responsibility |
|---|---|
| `proms_parser.py` | XML -> flat, dialect-tolerant `PromsMessage` field view |
| `message_types.py` | `MESSAGE_TYPE` -> bundle shape and entry order |
| `proms_fhir_transformer.py` | Bundle assembly + the `PromsFhirTransformer` queue class |
| `fhir_constants.py` | PSOM profile URLs, code systems, questionnaire canonicals |
| `source_systems.py` | `SYSTEM_ID` -> health board name / endpoint / PAS identifier system |
| `reference_data.py` | The wiki lookup tables + the `ReferenceDataResolver` seam |
| `mappers/message_header_mapper.py` | `MessageHeader` (always `entry[0]`) |
| `mappers/patient_mapper.py` | `Patient` (present in every message type) |
| `mappers/care_plan_mapper.py` | `CarePlan` (the PSOM pathway) |
| `mappers/task_mapper.py` | The EQ5D5L and Data Entry `Task`s |
| `mappers/participant_mappers.py` | `Practitioner`, `Organization` |
| `mappers/mapping_utils.py` | UUIDs, `meta.profile`, date/name helpers |

## Configuration

| Variable | Purpose |
|---|---|
| `WPAS_SOURCE_ENDPOINT_<SYSTEM_ID>` | Overrides that health board's `MessageHeader.source.endpoint` (e.g. `WPAS_SOURCE_ENDPOINT_108`) |

Service Bus, health check and logging configuration is inherited from
`transformer_base_lib` / `config.ini` in the usual way.

## Known limitations and open questions

These are annotated inline with `SPEC GAP` comments and need confirmation from the
specification owner:

- **No real WPAS XML sample has been supplied.** Element names are authoritative
  (the wiki's "From WPAS" column); the nesting used in the test fixtures is assumed.
- **The wiki defines no destination.** The spreadsheet's Promptly Health Collect
  endpoint is absent from it, so where these bundles are delivered is unresolved.
- **No Core Reference Data Lookup service** — see above. `Patient.gender` uses a
  local table and `Patient.communication` is never emitted.
- Only Swansea Bay (`108`) has a documented source name and endpoint. FHIR requires
  `MessageHeader.source.endpoint`, so unknown health boards fall back to
  `urn:nhs-wales:wpas:system-id:<SYSTEM_ID>` rather than a fabricated URL.
- `CarePlan.identifier.system` maps from `SYSTEM_ID`, a numeric code rather than a
  URI. Emitted verbatim to match Fiorano.
- `UPI_EVENT_DATE` is emitted as `Task.input.valueString`; the wiki does not state
  a type.
- The `deceasedBoolean` rule ("length > 2 TRUE, < 2 FALSE") leaves length exactly 2
  undefined; treated as not deceased.
- The referring GP's name is unavailable from WPAS; the wiki suggests a future WRDS
  lookup.
- `Patient.communication[1]` (non-preferred language) is `??` throughout the wiki
  and is not built.
- Date/time formats are unconfirmed, so parsing is tolerant of several formats.
  FHIR requires timezone-aware datetimes, so UTC is assumed.

## Running tests

```bash
uv sync
uv run python -m unittest discover tests
```

Full quality gate (ruff, bandit, mypy, unittest):

```bash
bash check.sh
```
