# proms_fhir_transformer

Queue-driven transformer converting **WPAS XML** into a **FHIR R4B message Bundle**
for **PROMS** (PSOM — Patient Standard Outcome Measures).

> **Naming note:** the directory and the `PromsFhirTransformer` class name date from
> an earlier assumption that the source was HL7v2-XML. The confirmed source format
> is a bespoke WPAS XML schema, so a rename to `proms_fhir_transformer` /
> `PromsFhirTransformer` is pending agreement.

## Source of truth

The two spreadsheets below are the **authoritative design source** for this
service:

- `PROMS Scenarios.xlsx` — the ten supported WPAS event scenarios, one row per
  scenario, including the `PROMS Message-TEMP` column that supplies the
  (currently placeholder) `eventCode` value routed on for each scenario.
- `WPAS PROMS Mapping - FHIR Review - By Profile-v1-0 - Final.xlsx` — the
  field-by-field mapping from WPAS payload fields to FHIR resource
  elements, one sheet per FHIR resource (MessageHeader, Patient, Encounter,
  Procedure, Appointment, Practitioner, Organization, Location).

An earlier version of this README described a different, wiki-based routing
model (`OPI`/`RFI`/`MPA` message types, a `CarePlan`/`Task` bundle shape driven
by the INSE Azure DevOps wiki's `WPAS_To_PROMS` Fiorano workflow design). That
model was **superseded** — the actual code, and this README, now follow the
`eventCode`-per-scenario model documented in the two spreadsheets above. The
old wiki-derived **field lookups** (NHS number certification, DHA code name,
PAS identifier system — see [Lookups ported from the wiki](#lookups-ported-from-the-wiki))
are still valid and still used; only the overall *routing/bundle-shape* model
was replaced.

## What this is

- Ingests a bespoke WPAS XML payload (**not** HL7v2-XML). None of the HL7 tooling
  used by the other transformers (`hl7_validation.xml_to_er7`, `hl7apy`,
  `field_utils_lib`) applies here.
- Routes on the WPAS `eventCode` field, falling back to the XML root element
  only when `eventCode` is missing (see [Message type routing](#message-type-routing)).
- Builds a FHIR **R4B** `Bundle` with `type = "message"` and a `MessageHeader` at
  `entry[0]`. Entry order is **positional and normative** — the mapping tables
  address entries by index.
- Every resource carries a `meta.profile` and a UUID id, cross-referenced
  between entries via `urn:uuid:` `fullUrl` values.
- Emits the Bundle as FHIR JSON to the egress queue.
- Mirrors the folder/module layout of `hl7_pims_transformer` (mappers/, tests/,
  Dockerfile, pyproject.toml, check.sh) for consistency with the rest of the repo.

## Message type routing

`message_types.py` encodes the whole routing table; `resolve_message_type()` is the
single decision point. Ten scenarios are supported, covering the original six
plus the four added by the "Include the additional WPAS PROMS event scenarios"
user story:

| `eventCode` | `MessageType.name` | Bundle entries | Notes |
|---|---|---|---|
| `REFERRAL` | `REFERRAL` | MessageHeader, Patient, ServiceRequest, PractitionerRole, Practitioner, Organization, Location | |
| `SURGERY` *(legacy fallback)*, `SURGERY-PROC` | `PROCEDURE_PERFORMED` | MessageHeader, Patient, Procedure, Practitioner, Organization, Location | `Procedure.status = "completed"` |
| `SURGERY-PERF` | `SURGERY_PERFORMED` | MessageHeader, Patient, Procedure, Practitioner, Organization, Location | Same shape as Procedure Performed |
| `SURGERY-DN` | `DISCHARGE` | MessageHeader, Patient, Encounter, Practitioner, Organization, Location | Encounter represents a discharge event |
| `PREOP` *(legacy fallback)*, `PREOP-AS` | `APPOINTMENT_SCHEDULED` | MessageHeader, Patient, Appointment, Practitioner, Organization, Location | `Appointment.status = "booked"` |
| `PREOP-VIS` | `OUTPATIENT_VISIT` | MessageHeader, Patient, Encounter, Practitioner, Organization, Location | Encounter represents an outpatient visit |
| `PREOP-AR` | `APPOINTMENT_RESCHEDULE` | MessageHeader, Patient, Appointment, Practitioner, Organization, Location | Appointment carries the updated date/time |
| `INPATIENT` | `INPATIENT_ADMISSION` | MessageHeader, Patient, Encounter, Practitioner, Organization, Location | |
| `CANCELLED` | `APPOINTMENT_CANCELLED` | MessageHeader, Patient, Appointment, Practitioner, Organization, Location | `Appointment.status = "cancelled"` |
| `PREREAD` | `PREADMISSION` | MessageHeader, Patient, Encounter, Practitioner, Organization, Location | Encounter represents a pre-admission event |

**TEMP / placeholder values — pending WPAS/spec owner confirmation:**

- `SURGERY-PROC`, `SURGERY-PERF`, `SURGERY-DN`, `PREOP-AS`, `PREOP-VIS`,
  `PREOP-AR` are placeholder `eventCode` values, taken from the `PROMS
  Message-TEMP` column the user added to `PROMS Scenarios.xlsx` to
  disambiguate `SURGERY` (previously shared by 3 scenarios) and `PREOP`
  (previously shared by 2 scenarios). Whether WPAS will actually emit these
  literal values is unconfirmed. Bare `SURGERY`/`PREOP` are kept as a legacy
  fallback so unmigrated payloads still route somewhere sensible.
- The Discharge `Encounter.status`/`Encounter.class` values are a placeholder
  red/bold addition the user made to the Encounter sheet of the "Final"
  mapping spreadsheet; not yet formally confirmed. `status="finished"` is
  used as given, but `class` reuses the valid v3 ActCode `IMP` / "Inpatient
  encounter" rather than the originally-suggested `DIS` — the v3 ActCode
  `EncounterClass` value set has no "discharge" code, since discharge isn't a
  distinct encounter class, just the same encounter reaching `finished`
  status (a Copilot PR review flagged the original `DIS` code as
  terminology-invalid).
- Appointment Reschedule has no dedicated `eventCode` in either spreadsheet
  scenario description — the acceptance criteria describe it purely as "an
  appointment update message ... when the date or time has changed" with no
  detection mechanism specified. `PREOP-AR` was adopted as a placeholder
  routing code (this service is stateless and has no prior-message store to
  compare against, so genuine change-detection is out of scope as currently
  implemented).

Code marked `# TEMP` in `fhir_constants.py`, `message_types.py`, and
`mappers/encounter_mapper.py` traces directly back to these placeholder
values.

Unroutable messages (unknown `eventCode`, and no matching root element) raise
`ValueError`, so `process_message` records a transformation failure rather
than emitting an incorrect bundle. This satisfies the "reject unsupported or
invalid events" acceptance criterion without any PROMS-specific error-handling
code — dead-lettering/retry is inherited from `BaseTransformer`/
`processor_manager_lib`.

## WPAS source fields

Fields observed in real SIT payload samples (root element `<PromsEventRequest>`):
`system_id`, `hbCode`, `eventCode`, `eventDate`, `eventPathway`, `pathway`,
`activityNotekey`, `nhsNumber`, `crn`, `patientTitle`, `patientFirstname`,
`patientMiddlename`, `patientSurname`, `gender`, `dob`, `buildingName`,
`streetRoadName`, `postTown`, `postCode`, `postalCounty`,
`preferred_spoken_language_code`, `spoken_language`, `referrer_code`,
`referrer_name`, `referrer_location`, `referrer_postcode`, `referrer_org`,
`dhaCode`, `consultant_code`, `clinicianName`, `consultant_specialty`,
`main_specialty_name`, `appointmentDate`, `appointmentTime`, `CONFIRM_APPT`.

`proms_parser.normalise_key()` lower-cases and strips separators, so a single
lookup tolerates dialect variation (`nhsNumber` ≡ `NHS_NUMBER` ≡ `nhs-number`).
Leaf elements are indexed regardless of nesting depth and namespace prefixes are
stripped, so changes to the payload's element hierarchy do not require parser
changes. `MESSAGE_TYPE` is also accepted as a legacy alias for `eventCode`.

XML is parsed with `defusedxml`, matching the convention in
`shared_libs/hl7_validation`.

## Lookups ported from the wiki

`reference_data.py` and `source_systems.py` port three lookup functions from the
INSE Azure DevOps wiki's earlier `WPAS_To_PROMS` Fiorano workflow design
verbatim, including their behaviour of **returning the input unchanged** when a
code is unrecognised. These lookups are still valid and still used even though
the overall routing/bundle-shape model they came from has been superseded (see
[Source of truth](#source-of-truth)):

| Function | Purpose |
|---|---|
| `nhs_certification_display()` | `NHS_CERTIFICATION` `01`–`08` -> NHS number verification status text |
| `dha_code_name()` | `DHA_CODE` `7A1`/`7A2`/`7A3`/`7A5`/`7A6`/`7A7` -> health board name (note: no `7A4`) |
| `get_pas_identifier_system()` | `SYSTEM_ID`/`hbCode` -> the health board's PAS identifier URL |

## The Core Reference Data gap

There is no Core Reference Data lookup service available anywhere in the
Integration Hub for resolving gender/language codes from WPAS.

This is modelled as a `ReferenceDataResolver` Protocol so the seam is explicit and
replaceable. The shipped `StaticReferenceDataResolver`:

- maps `gender` to a FHIR `administrative-gender` code locally, and
- always returns `None` for language codes; `Patient.communication` is only emitted when a display
  value (e.g. `spoken_language`) is present in the payload.

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
additive and default to the previous behaviour, so `transformers/hl7_phw_transformer`,
`hl7_chemo_transformer` and `hl7_pims_transformer` are unaffected.

A standalone convenience entry point is also available for ad-hoc use and testing:

```python
from xml_fhir_proms_transformer.proms_transformer import transform_proms_xml_to_fhir_bundle

bundle = transform_proms_xml_to_fhir_bundle(wpas_xml_message)
print(bundle.model_dump_json(indent=2))
```

`build_fhir_bundle()` accepts an injectable `uuid_factory`, which the tests use to
produce deterministic bundles.

## Module layout

| Module | Responsibility |
|---|---|
| `proms_parser.py` | XML -> flat, dialect-tolerant `PromsMessage` field view |
| `message_types.py` | `eventCode` -> bundle shape, entry order and FHIR metadata (`MESSAGE_TYPES_BY_CODE`, `resolve_message_type()`) |
| `proms_transformer.py` | Bundle assembly + the `PromsFhirTransformer` queue class |
| `fhir_constants.py` | Profile URLs, code systems, eventCoding codes/displays |
| `source_systems.py` | `system_id`/`hbCode` -> health board name / endpoint / PAS identifier system |
| `reference_data.py` | The wiki-derived lookup tables + the `ReferenceDataResolver` seam |
| `mappers/message_header_mapper.py` | `MessageHeader` (always `entry[0]`) |
| `mappers/patient_mapper.py` | `Patient` (present in every message type) |
| `mappers/service_request_mapper.py` | `ServiceRequest` (Referral bundle) |
| `mappers/practitioner_role_mapper.py` | `PractitionerRole` (Referral bundle) |
| `mappers/procedure_mapper.py` | `Procedure` (Procedure Performed, Surgery Performed) |
| `mappers/appointment_mapper.py` | `Appointment` (Appointment Scheduled, Cancelled, Reschedule) |
| `mappers/encounter_mapper.py` | `Encounter` (Inpatient Admission, Preadmission, Outpatient Visit, Discharge) |
| `mappers/participant_mappers.py` | `Practitioner`, `Organization` |
| `mappers/location_mapper.py` | `Location` |
| `mappers/mapping_utils.py` | UUIDs, `meta.profile`, date/name helpers |
| `mappers/_deprecated/` | Retired mappers (`care_plan_mapper.py`, `task_mapper.py`) from the superseded wiki-based `OPI`/`RFI`/`MPA` model; kept for reference only, not imported by any active code |

## Configuration

| Variable | Purpose |
|---|---|
| `WPAS_SOURCE_ENDPOINT_<SYSTEM_ID>` | Overrides that health board's `MessageHeader.source.endpoint` (e.g. `WPAS_SOURCE_ENDPOINT_108`) |

Service Bus, health check and logging configuration is inherited from
`transformer_base_lib` / `config.ini` in the usual way.

## Known limitations and open questions

These are annotated inline with `SPEC GAP`/`TEMP` comments and need confirmation
from the specification owner:

- **Placeholder eventCode scheme.** `SURGERY-PROC`/`SURGERY-PERF`/`SURGERY-DN`
  and `PREOP-AS`/`PREOP-VIS`/`PREOP-AR` are TEMP values pending confirmation
  that WPAS will emit distinct `eventCode` values per scenario (see
  [Message type routing](#message-type-routing)).
- **Discharge Encounter values are placeholders.** `status="finished"` is a
  TEMP red/bold addition the user made to the Encounter sheet of the "Final"
  mapping spreadsheet; not yet formally confirmed by WPAS/the spec owner.
  `class.code`/`class.display` reuse the valid v3 ActCode `IMP` / "Inpatient
  encounter" (not the originally-suggested `DIS`, which is not a valid
  `EncounterClass` code — flagged by a Copilot PR review) since discharge is
  represented by encounter status, not a distinct class.
- **No real WPAS sample data for the four new scenarios** (Surgery Performed,
  Outpatient Visit, Discharge Notification, Appointment Reschedule) — the test
  fixtures for these are dummy/best-guess values modelled on the existing
  SURGERY/PREOP samples, not real SIT payloads.
- **Appointment Reschedule has no real detection mechanism.** The acceptance
  criteria describe it as "an appointment update ... when the date or time has
  changed", which implies comparing against a prior message; this service is
  stateless, so `PREOP-AR` is currently routed purely on `eventCode`.
- **No documented destination** in the WPAS mapping spreadsheets for where
  these bundles are delivered outside of the fixed Promptly Collect endpoint
  hardcoded in `fhir_constants.py`.
- `MessageHeader.meta.profile` value was flagged by a reviewer as likely
  incorrect; awaiting a confirmed NHS Wales URL.
- **No Core Reference Data Lookup service** exists in the Integration Hub —
  `Patient.gender` uses a local table and `Patient.communication` is only
  emitted when a display value is present in the payload.
- Only a subset of health boards have a documented source name and endpoint
  in `source_systems.py`. FHIR requires `MessageHeader.source.endpoint`, so
  unknown/missing `system_id`/`hbCode` values fall back to a placeholder
  `https://wpas-source.invalid/system-id/<value>` URL rather than a fabricated
  real one.
- `ServiceRequest.identifier.value` — no WPAS source field is specified in the
  mapping spreadsheet for the Referral scenario; `pathway` is used as the best
  available unique identifier pending confirmation.
- `Appointment`/`AppointmentParticipant.status` for the practitioner
  participant has no confirmed business rule (only the patient participant's
  `CONFIRM_APPT` rule is documented); defaults to `"accepted"`.
- WPAS supplies a single appointment date/time with no duration or end time,
  so `Appointment.end` is set equal to `Appointment.start` as a placeholder.
- `Location.name` is derived from the first line of the free-text
  `referrer_location` field; the mapping spreadsheet does not specify a
  dedicated name field.
- `Patient.communication` (written language) field names (`preferred_written_language_code` etc.)
  are not yet confirmed against a real WPAS payload.
- Date/time formats are unconfirmed, so parsing is tolerant of several
  formats. FHIR requires timezone-aware datetimes, so UTC is assumed.


## Running tests

```bash
uv sync
uv run python -m unittest discover tests
```

Full quality gate (ruff, bandit, mypy, unittest):

```bash
bash check.sh
```
