# PROMS FHIR Mapping Analysis

> Authored by Binky | Reviewed with Matt | August 2026  
> Source documents: `PROMS Scenarios.xlsx` and `WPAS PROMS Mapping - FHIR Review - By Profile-v1-0.xlsx`

---

## 1. Overview

This document analyses two source Excel spreadsheets that together define the complete FHIR R4 mapping 
from the WPAS PAS system to the Promptly Health PROMS (PSOM) platform. It identifies:

- The full set of **clinical event scenarios** and the FHIR bundle each produces
- The **field-level FHIR profile mapping** for every resource type
- **Gaps, corrections and open questions** raised in the spreadsheets
- What this means for the current `xml_fhir_proms_transformer` implementation

> **Important note on scope:** The row `Patient demographics update (MPA/MPR)` in the Scenarios sheet 
> has been explicitly excluded from this analysis at the request of the specification owner.

---

## 2. PROMS Scenarios (Spreadsheet 1)

This spreadsheet defines **11 active clinical event scenarios** (excluding MPA/MPR). Each maps a real-world 
clinical event in WPAS to a PROMS message type and a FHIR bundle shape.

### 2.1 Scenario → Bundle mapping table

| # | Clinical Scenario | PROMS Event Type | FHIR Bundle Name | Bundle Contents |
|---|---|---|---|---|
| 1 | **Patient Referral** | `REFERRAL` | WPAS Referral Bundle | MessageHeader, Patient, **ServiceRequest** |
| 2 | **Procedure performed** | `SURGERY` | WPAS Procedure Bundle | MessageHeader, Patient, **Procedure** |
| 3 | **Appointment scheduled** | `PREOP` | WPAS Appointment Bundle | MessageHeader, Patient, **Appointment** |
| 4 | **Inpatient admission** | `INPATIENT` | WPAS Encounter Bundle | MessageHeader, Patient, **Encounter** |
| 5 | **Appointment cancellation** | `CANCELLED` | WPAS Appointment Cancellation Bundle | MessageHeader, Patient, Appointment *(status: cancelled)* |
| 6 | **Appointment rescheduling** | *(same as scheduled)* | WPAS Appointment Reschedule Bundle | MessageHeader, Patient, Appointment *(updated date/time)* |
| 7 | **Pre-admission notification** | `PREREAD` | WPAS Preadmission Bundle | MessageHeader, Patient, Encounter *(pre-admission)* |
| 8 | **Surgery performed** | `SURGERY` | WPAS Surgery Bundle | MessageHeader, Patient, Procedure *(surgery)* |
| 9 | **Outpatient visit** | `PREOP` | WPAS Outpatient Bundle | MessageHeader, Patient, Encounter *(outpatient)* |
| 10 | **Discharge notification** | `SURGERY` | WPAS Discharge Bundle | MessageHeader, Patient, Encounter *(discharge)* |
| 11 | **Subscribe to patient demographics update** | *(no mapping defined)* | *(no bundle defined)* | *(empty row — future scope)* |

### 2.2 Key observations from Scenario sheet

- **Every bundle** contains `MessageHeader` + `Patient` as entries [0] and [1]
- The **third entry** (entry[2]) varies by event type:
  - `ServiceRequest` for referrals
  - `Procedure` for surgical/procedure events
  - `Appointment` for scheduling events
  - `Encounter` for inpatient/outpatient/admission/discharge events
- `SURGERY` event type is shared across three different scenarios (procedure, surgery, discharge)
- `PREOP` event type is shared between appointment scheduled and outpatient visit
- The current transformer code builds **none** of these bundles — it currently only handles the 
  older PSOM `CarePlan`/`Task` model from the original wiki. **This is the primary gap.**

---

## 3. FHIR Profile Mapping (Spreadsheet 2)

This spreadsheet contains 10 tabs — one per FHIR resource profile. Each tab maps WPAS source fields 
to FHIR element paths, with must-support flags, cardinality, hardcoded values, notes, and per-scenario 
columns.

### 3.1 Column structure (all sheets)

| Column | Description |
|---|---|
| Snapshot Table | Full FHIR path (e.g. `MessageHeader.eventCoding.code`) |
| Key Elements Table | Shorter reference path used in bundle context |
| Must Support | `MS` flag — critical elements |
| Cardinality | FHIR cardinality |
| Value | ValueSet binding or fixed value description |
| WPAS Segments | Source field name(s) from WPAS payload (both camelCase and UPPER_SNAKE variants) |
| Hardcoded Values | Fixed values to use regardless of WPAS input |
| Notes | Implementation notes from the WPAS team |
| FHIR comments | Reviewer corrections/questions |
| *(Scenario columns)* | One column per scenario — all say "See comments" indicating pending confirmation |

---

### 3.2 MessageHeader (entry[0] in all bundles)

**Profile:** `https://fhir.promptly.health/wpas/StructureDefinition/wpas-messageheader`  
*(Note: FHIR reviewer flags this as incorrect — should be a real NHS Wales profile)*

| FHIR Element | Cardinality | Source / Hardcoded | Notes / Issues |
|---|---|---|---|
| `MessageHeader.id` | — | UUID (generated) | `MessageHeaderUUID` |
| `MessageHeader.meta.profile` | — | `https://fhir.promptly.health/wpas/StructureDefinition/wpas-messageheader` | ⚠️ Reviewer: incorrect profile URL |
| `MessageHeader.eventCoding.system` | 0..1 | `https://fhir.promptly.health/wpas/CodeSystem/wpas-event-codes` | |
| `MessageHeader.eventCoding.code` | 1..1 MS | From WPAS `eventCode` field | Must come from `VS: WPAS Event (required)` |
| `MessageHeader.destination.name` | 0..1 | `"FHIR Promptly Collect"` (hardcoded) | |
| `MessageHeader.destination.endpoint` | 1..1 | `https://collect.promptlyhealth.com/fhir` (hardcoded) | **NEW** — not in current code |
| `MessageHeader.sender` | 0..1 | Reference → Organization | ⚠️ Reviewer: THIS IS REQUIRED — use for HB name |
| `MessageHeader.source.name` | 0..1 | From `system_id` / `SYSTEM_ID` | If 108 → "Swansea Bay Health Board" |
| `MessageHeader.source.endpoint` | 1..1 | From `system_id` | ⚠️ Reviewer: must be a URL |
| `MessageHeader.focus` | 1..* MS | Patient UUID, ServiceRequest UUID, PractitionerRole UUID, Procedure UUID, etc. | ⚠️ Reviewer: focus list changes per bundle type |
| `MessageHeader.definition` | 0..1 | canonical(messageDefinition) | |

**⚠️ Critical differences from current code:**
- `eventCoding.code` must now come from `eventCode` WPAS field mapped to `VS: WPAS Event` — **not** `psom-request`/`patient-update` hardcoded values
- A **`destination`** block is now required (Promptly Collect endpoint)
- `sender` is recommended for health board identification
- `focus` references change per bundle (ServiceRequest vs Procedure vs Encounter vs Appointment)

---

### 3.3 Patient (entry[1] in all bundles)

**Profile:** `https://fhir.nhs.wales/StructureDefinition/DataStandardsWales-Patient` ✅ (same as current)

| FHIR Element | Cardinality | Source / Hardcoded | Notes |
|---|---|---|---|
| `Patient.id` | — | UUID | |
| `Patient.meta.profile` | — | DSW-Patient | |
| `Patient.identifier` (NHS number) | 1..* MS | `nhsNumber` / `NHS_NUMBER` | System: `https://fhir.nhs.uk/Id/nhs-number` |
| `Patient.identifier` (PAS) | 0..* | `crn` / `UNIT_NUMBER` | System: `https://fhir.{hb}.nhs.wales/Id/pas-identifier` from `system_id` |
| `Patient.name.family` | 0..1 MS | `patientSurname` / `SURNAME` | |
| `Patient.name.given` | 0..1 MS | `patientFirstname` / `FORENAME` | |
| `Patient.name.prefix` | 0..* MS | *(not currently mapped)* | ⚠️ Is WPAS title data from Core Reference Data standard? |
| `Patient.telecom` | 0..* MS | `TELEPHONE_DAY` | **NEW** — not in current code |
| `Patient.gender` | 0..1 MS | `gender` / `SEX` | AdministrativeGender VS — note: BirthSex ≠ Gender |
| `Patient.birthDate` | 0..1 MS | `dob` / `BIRTHDATE` | |
| `Patient.deceasedDateTime` | 0..1 | `DEATHDATE` | ⚠️ Changed from `deceasedBoolean` → `deceasedDateTime` |
| `Patient.address.line` | 0..* | `buildingName + streetRoadName` / `ADDRESS_1` | **NEW** — concatenation of two fields |
| `Patient.address.city` | 0..1 | `postTown` / `ADDRESS_2` | **NEW** |
| `Patient.address.postalCode` | 0..1 MS | `postCode` / `POSTCODE` | ✅ already mapped |
| `Patient.communication.language` | 1..1 MS | `PREFERRED_LANGUAGE` | Still pending Core Reference Data service |

**⚠️ Critical differences from current code:**
- `deceasedBoolean` → **`deceasedDateTime`** (the new mapping uses the actual date value, not a boolean)
- `Patient.telecom` mapping to `TELEPHONE_DAY` is new
- `Patient.address.line` = concat of `ADDRESS_1` (new WPAS field)
- `Patient.address.city` = `ADDRESS_2` (new WPAS field)

---

### 3.4 ServiceRequest (entry[2] — Referral bundle only)

**Profile:** `https://fhir.hl7.org.uk/StructureDefinition/UKCore-ServiceRequest`  
*(Reviewer flags as incorrect — needs WPAS-specific profile)*

| FHIR Element | Cardinality | Source / Hardcoded | Notes |
|---|---|---|---|
| `ServiceRequest.id` | — | UUID | `ServiceRequestUUID` |
| `ServiceRequest.identifier.system` | 1..1 | `https://wpas-integration-ig.tools.labs.promptly.health/id/wpas-servicerequest` | |
| `ServiceRequest.identifier.value` | 1..1 MS | *(WPAS identifier value — TBC)* | |
| `ServiceRequest.status` | 1..1 MS | `"Active"` (hardcoded) | |
| `ServiceRequest.intent` | 1..1 MS | `"Planned"` (hardcoded) | |
| `ServiceRequest.code.coding.code` | 0..1 | `eventPathway` | WPAS source field |
| `ServiceRequest.code.coding.display` | 0..1 | `"Referral"` (hardcoded) | |
| `ServiceRequest.subject.reference` | — | Patient UUID | |
| `ServiceRequest.occurrenceDateTime` | 0..1 | `eventDate` | |
| `ServiceRequest.requester.reference` | 0..1 | PractitionerRole UUID | |

**→ This is an entirely new resource not in the current transformer.**

---

### 3.5 PractitionerRole (entry[3] — Referral bundle)

**Profile:** `https://fhir.nhs.wales/StructureDefinition/DataStandardsWales-PractitionerRole`

| FHIR Element | Cardinality | Source / Hardcoded | Notes |
|---|---|---|---|
| `PractitionerRole.id` | — | UUID | |
| `PractitionerRole.identifier.system` | 1..1 | `https://wpas-integration-ig.tools.labs.promptly.health/id/wpas-practitionerrole` | |
| `PractitionerRole.practitioner.reference` | 0..1 | Practitioner UUID | Links to entry[4] |
| `PractitionerRole.organization.reference` | 0..1 | Organization UUID | Links to entry[5] |
| `PractitionerRole.speciality.coding.code` | 0..* MS | `consultant_specialty` | Must match UKCorePracticeSettingCode |
| `PractitionerRole.location.reference` | 0..* | Location UUID | Links to entry[6] |

**→ This is an entirely new resource not in the current transformer.**

---

### 3.6 Practitioner (entry[4])

**Profile:** `https://fhir.nhs.wales/StructureDefinition/DataStandardsWales-Practitioner` ✅ (same base as current)

| FHIR Element | Source | Notes |
|---|---|---|
| `Practitioner.identifier.system` | Hardcoded: `https://fhir.hl7.org.uk/Id/gmc-number` | ✅ same as current |
| `Practitioner.identifier.value` | `referrer_code` / `consultant_code` | **Different WPAS field names from current** |
| `Practitioner.name.family` | `referrer_name` / `clinicianName` | Split required — "surname, given name" format |
| `Practitioner.name.given` | `referrer_name` / `clinicianName` | Same source as family |

---

### 3.7 Organization (entry[5])

**Profile:** `https://fhir.nhs.wales/StructureDefinition/DataStandardsWales-Organization` ✅ (same as current)

| FHIR Element | Source | Notes |
|---|---|---|
| `Organization.identifier.system` | Hardcoded: `https://fhir.nhs.uk/Id/ods-organization-code` | ✅ same as current |
| `Organization.identifier.value` | *(from ODS code)* | |
| `Organization.name` | `referrer_org` | **New WPAS field** — previously derived from DHA_CODE lookup |

---

### 3.8 Location (entry[6] — Referral bundle)

**Profile:** `https://fhir.nhs.wales/StructureDefinition/DataStandardsWales-Location`  
**→ New resource not in current transformer.**

| FHIR Element | Source | Notes |
|---|---|---|
| `Location.identifier.system` | `https://fhir.nhs.wales/Id/wrts-location-identifier` | |
| `Location.identifier.value` | `referrer_location` | New WPAS field |
| `Location.name` | *(required, no WPAS source defined)* | ⚠️ "Huw to put stuff in payload" |
| `Location.address.postalCode` | `referrer_postcode` | New WPAS field |

---

### 3.9 Encounter (entry[2] — Inpatient/Pre-admission/Outpatient/Discharge bundles)

**Profile:** `https://fhir.hl7.org.uk/StructureDefinition/UKCore-Encounter`

| FHIR Element | Source / Hardcoded | Notes |
|---|---|---|
| `Encounter.status` | `In-progress` / `finished` | Depends on scenario |
| `Encounter.class.system` | `http://terminology.hl7.org/CodeSystem/v3-ActCode` | |
| `Encounter.class.code` | `IMP` / `PRENC` / `AMB` | Inpatient / Pre-admission / Ambulatory |
| `Encounter.subject.reference` | Patient UUID | |

---

### 3.10 Procedure (entry[2] — Procedure/Surgery bundles)

**Profile:** `https://fhir.hl7.org.uk/StructureDefinition/UKCore-Procedure`

| FHIR Element | Source / Hardcoded | Notes |
|---|---|---|
| `Procedure.status` | `"Yes"` (hardcoded) | ⚠️ Reviewer: must be from `HL7 EventStatus` VS — "Yes" is not valid |
| `Procedure.code` | `eventPathway` | |
| `Procedure.subject.reference` | Patient UUID | |
| `Procedure.performedDateTime` | `appointmentDate + appointmentTime` | Concat + format |

---

### 3.11 Appointment (entry[2] — Appointment Scheduled/Cancelled bundles)

**Profile:** `https://fhir.hl7.org.uk/StructureDefinition/UKCore-Appointment`

| FHIR Element | Source / Hardcoded | Notes |
|---|---|---|
| `Appointment.status` | `eventCode` (WPAS field) | Must match `HL7 AppointmentStatus` VS |
| `Appointment.serviceType` | `main_specialty_name` | |
| `Appointment.start` | `appointmentDate + appointmentTime` | |
| `Appointment.end` | `appointmentDate + appointmentTime` | |
| `Appointment.participant.actor.reference` | Practitioner UUID | |
| `Appointment.participant.status` | *(required)* | Must match `HL7 ParticipationStatus` VS |

---

## 4. Bundle Structure Summary

| Bundle | entry[0] | entry[1] | entry[2] | entry[3] | entry[4] | entry[5] | entry[6] |
|---|---|---|---|---|---|---|---|
| **Referral** | MessageHeader | Patient | ServiceRequest | PractitionerRole | Practitioner | Organization | Location |
| **Procedure performed** | MessageHeader | Patient | Procedure | — | Practitioner | Organization | Location |
| **Appointment Scheduled** | MessageHeader | Patient | Appointment | — | Practitioner | Organization | Location |
| **Inpatient admission** | MessageHeader | Patient | Encounter | — | Practitioner | Organization | Location |
| **Appointment cancellation** | MessageHeader | Patient | Appointment *(cancelled)* | — | Practitioner | Organization | Location |
| **Appointment rescheduling** | MessageHeader | Patient | Appointment *(rescheduled)* | — | Practitioner | Organization | Location |
| **Pre-admission notification** | MessageHeader | Patient | Encounter *(pre-admission)* | — | Practitioner | Organization | Location |
| **Surgery performed** | MessageHeader | Patient | Procedure *(surgery)* | — | Practitioner | Organization | Location |
| **Outpatient visit** | MessageHeader | Patient | Encounter *(outpatient)* | — | Practitioner | Organization | Location |
| **Discharge notification** | MessageHeader | Patient | Encounter *(discharge)* | — | Practitioner | Organization | Location |

---

## 5. What Needs to Change in the Code

### 5.1 Fundamental model changes

The current transformer is based on the **old PSOM CarePlan/Task model** from the ADO wiki. 
The new spreadsheets describe a **completely different Promptly Health WPAS integration model**. 
The key differences are:

| Area | Current (Wiki / PSOM model) | New (Spreadsheet / Promptly model) |
|---|---|---|
| Event routing | OPI / RFI / MPA | REFERRAL / SURGERY / PREOP / INPATIENT / CANCELLED / PREREAD |
| MessageHeader profile | DSW-PSOM-MessageHeader | `wpas-messageheader` (Promptly IG) |
| eventCoding | `psom-request` / `patient-update` | `eventCode` from WPAS payload |
| entry[2] resource | CarePlan | ServiceRequest / Procedure / Encounter / Appointment |
| entry[2]/[3] | Task(EQ5D5L) / Task(DataEntry) | PractitionerRole (referral only) |
| Practitioner id field | `CONS_GMC` / `REFERRING_GP` | `consultant_code` / `referrer_code` |
| Organization name | Derived from `DHA_CODE` lookup | `referrer_org` field from payload |
| Location | Not present | New resource — `referrer_location` / `referrer_postcode` |
| Patient.deceased | `deceasedBoolean` | `deceasedDateTime` (actual date value) |
| Patient.address | postalCode only | postalCode + line (ADDRESS_1) + city (ADDRESS_2) |
| Destination | Not present | Required — Promptly Collect endpoint |

### 5.2 New WPAS source fields required

The following WPAS fields appear in the mapping but are **not currently parsed or mapped**:

| WPAS Field | Used In |
|---|---|
| `eventCode` | MessageHeader.eventCoding.code |
| `eventPathway` | ServiceRequest.code / Procedure.code |
| `eventDate` | ServiceRequest.occurrenceDateTime |
| `appointmentDate` + `appointmentTime` | Procedure.performedDateTime / Appointment.start+end |
| `TELEPHONE_DAY` | Patient.telecom |
| `ADDRESS_1` | Patient.address.line |
| `ADDRESS_2` | Patient.address.city |
| `referrer_code` | Practitioner.identifier (referral) |
| `consultant_code` | Practitioner.identifier (procedure/appointment) |
| `referrer_name` | Practitioner.name (referral) |
| `referrer_org` | Organization.name |
| `referrer_location` | Location.identifier.value |
| `referrer_postcode` | Location.address.postalCode |
| `consultant_specialty` | PractitionerRole.speciality |
| `main_specialty_name` | Appointment.serviceType |

### 5.3 Open questions / gaps that need answering before coding

1. **`Procedure.status` hardcoded value** — spreadsheet says `"Yes"` but FHIR requires a valid `EventStatus` code (`preparation` / `in-progress` / `completed` etc.). What is the correct code?
2. **`MessageHeader.sender`** — reviewer says this is required. Should it reference the Organization entry?
3. **`ServiceRequest.identifier.value`** — no WPAS source field is specified. Which WPAS field provides the service request identifier?
4. **`Location.name`** — noted as "Huw to put stuff in payload". Is this data available yet?
5. **`PractitionerRole.identifier.value`** — no WPAS source field specified.
6. **All scenario columns say "See comments"** — the per-scenario mapping confirmation is still pending. Are we confident that the bundle structure table above is correct?
7. **`Patient.deceasedDateTime`** vs the old `deceasedBoolean` — can WPAS actually provide a FHIR-formatted datetime?
8. **`MessageHeader.meta.profile`** — reviewer says the Promptly IG URL is incorrect. What is the correct DSW profile URL for the new model?

---

## 6. Reviewer Comments Summary

The FHIR reviewer raised the following consistent issues across all sheets:

| Issue | Affected Sheets |
|---|---|
| `meta.profile` URL is a Promptly IG URL, not the correct NHS Wales/HL7 base URL | All sheets |
| `MessageHeader.sender` is required (use for HB name) | MessageHeader |
| `MessageHeader.destination` requires real data (Promptly Collect endpoint) | MessageHeader |
| `MessageHeader.responsible` — should these be WPAS profiles? | MessageHeader |
| `Procedure.status = "Yes"` is not a valid FHIR code | Procedure |
| `Procedure.actor.reference` element does not exist in FHIR | Procedure |
| `PractitionerRole.identifier` — use correct system URL | PractitionerRole |
| `ServiceRequest.identifier` — use correct system URL | ServiceRequest |
| `Patient.communication.language` is Must Support (even though parent `communication` is not) | Patient |

---

*Document generated: 2026-08-10. Next step: confirm open questions with specification owner, then implement mapping changes.*
