# PROMS FHIR Mapping Analysis — v2

> Authored by Binky | Reviewed with Matt | September 2026
> Source document: `WelshPAS to Integration Hub PROMs Mapping.xlsx`
> Supersedes / extends: `PROMS_FHIR_Mapping_Analysis.md` (August 2026)

---

## 1. Overview

This spreadsheet is a more concrete, later-stage version of the mapping than the one analysed in
`PROMS_FHIR_Mapping_Analysis.md`. It uses a tighter column structure per sheet:

| Column | Meaning |
|---|---|
| FHIR Segment | Target FHIR element path |
| Exists? | Is this WelshPAS field actually sent in the payload today (`Y`/`N`) |
| WelshPAS XML Element | Source field name in the WPAS payload |
| Defaulted in IH | Value the **Integration Hub transformer itself** must supply (not from WPAS) |
| MS | Must Support flag |
| Cardinality | FHIR cardinality |
| Standard | `National` / `Local` — which code system/valueset applies |
| Comments | Implementation notes, business rules, valuesets |

This analysis cross-references every row against the current `xml_fhir_proms_transformer` code to
classify each item as: **already correct**, **needs changing**, **new field to add**, or **external
lookup required** (data not in the WPAS payload at all — needs a reference table or downstream service).

---

## 2. MessageHeader

| FHIR Element | Source / Default | Status vs current code |
|---|---|---|
| `eventCoding` | `eventCode`: `referral \| procedure \| appointment \| encounter \| patient-update` | 🔴 **Changed** — current code routes on `REFERRAL/SURGERY/PREOP/INPATIENT/CANCELLED/PREREAD`. New value set is smaller (5 values, lowercase) and reintroduces `patient-update` (previously out of scope). |
| `destination` | Defaulted in IH → "Promptly AA" | 🟢 Matches current (`PROMPTLY_COLLECT_DESTINATION_NAME`/`_ENDPOINT`), naming aside |
| `source` | `system_id`, cardinality now **1..1** | 🟡 Current code treats `system_id` as optional with `hbCode` fallback — cardinality says it should always be present |
| `reason` | *(no WPAS field)* — `admit \| discharge \| moved \| edit` | 🆕 **New element, not modelled at all.** Looks like it *qualifies* eventCoding (e.g. `encounter` + `reason=discharge`), which may explain how our old INPATIENT/PREREAD/discharge/outpatient scenarios collapse into one eventCoding value. |

**⚠️ Open question:** does `eventCoding` + `reason` together replace our current 6-way `MessageType`
routing table? e.g. `encounter` + `reason=admit` → inpatient admission, `encounter` + `reason=discharge`
→ discharge, `encounter` + `reason=moved` → transfer? Needs confirming before we touch `message_types.py`.

---

## 3. Patient

| FHIR Element | Source | Status |
|---|---|---|
| `identifier:[hb]PasIdentifier` | `crn` | 🟢 Matches current `_pas_identifier()` |
| `identifier:nhsNumber` | `nhsNumber` | 🟢 Matches |
| `identifier.system` | `system_id`, now **1..1** | 🟡 Same cardinality note as MessageHeader.source |
| `active` | Defaulted in IH | 🆕 Not currently set — need a default (likely `true`) |
| `name.family` / `name.given` / `name.prefix` | `patientSurname` / `patientFirstname`+`patientMiddlename` / `patientTitle` | 🟢 Matches |
| `name.suffix` | *(nothing to send)* | ➖ No action — confirmed no source data |
| `telecom` | `home_phone`, `work_phone`, `mobile_phone`, `email` (all currently `Exists? N`) | 🆕 **New — not modelled.** 4 separate telecom entries, not the single `TELEPHONE_DAY` we guessed from the previous spreadsheet. Not live in payloads yet but should be built defensively. |
| `gender` | `gender` | 🟢 Matches |
| `birthDate` | `dob` (`YYYY-MM-DD`) | 🟢 Matches |
| `deceased` | `dod` — WelshPAS sends datetime OR IH defaults to boolean | 🟢 **Confirms current dual `bool`/`datetime` approach is correct.** Only change: source field is `dod`, not `DEATHDATE` — need to check both are accepted aliases. |
| `address.line` | `buildingName` + `streetRoadName` | 🟢 Matches |
| `address.city` | `postTown` | 🟢 Matches |
| `address.district` | `postalCounty` | 🆕 **New — not modelled** |
| `address.postalCode` | `postCode` | 🟢 Matches |
| `maritalStatus` | `MARITAL` | 🆕 **New — not modelled** |
| `extension:ethnicCategory` | `ETHNIC_ORIGIN` | 🆕 **New — not modelled** |
| `extension:religion` | `RELIGION` | 🆕 **New — not modelled** |
| `extension:contactPreference` | *preferred spoken language* | 🔴 **Correction needed.** Current `_communication()` conflates spoken + written language into one `Patient.communication.language`. Spoken language should be a separate `contactPreference` extension. |
| `communication.language` | *preferred written language* | 🔴 Same correction — this element should carry **written** language only. |

---

## 4. ServiceRequest

| FHIR Element | Source / Default | Status |
|---|---|---|
| `status` | Defaulted in IH (no fixed value given) | 🟡 Current code hardcodes `"Active"` — need the specific default value confirmed against FHIR's `RequestStatus` valueset (should be lowercase `active` etc.) |
| `intent` | Defaulted in IH | 🟡 Current code hardcodes `"Planned"` — same casing concern (`RequestIntent` valueset uses `plan`, `order`, `proposal` — **not** `"Planned"**) |
| `code` | *(no direct field)* — "IH to query SNOMED" | 🔴 **New requirement.** Current code just passes `eventPathway` through as a free-text code. Spec now implies a SNOMED lookup/translation step is needed — WelshPAS itself has no SNOMED codes for PROMs. |

---

## 5. PractitionerRole

| FHIR Element | Source | Status |
|---|---|---|
| `identifier.value` | `specialty_name` | 🟢 **Answers previous SPEC GAP** — use `specialty_name`, not an unspecified field |
| `active` | Defaulted in IH → active | 🆕 Not currently set |
| `period` | Defaulted in IH → blank | ➖ No action needed |
| `practitioner` | `consultant_code` (reference link) | 🟢 Matches current reference wiring |
| `organization` | Defaulted in IH → national HB code, e.g. `7A1` | 🔴 **Correction.** Current `map_organization()` prefers `referrer_org` from payload; spec says `PractitionerRole.organization` should default to the health-board ODS code, independent of `referrer_org`. |
| `specialty` | `consultant_specialty` | 🟢 Matches |
| `telecom` | `CONS.CONTACT_TELNO` / `CONS.EMAIL` (usually blank) | ➖ Low priority — build defensively but rarely populated |

---

## 6. Practitioner

| FHIR Element | Source | Status |
|---|---|---|
| `name` | `clinicianName` | 🟢 Matches |

**Note:** this sheet does **not** list a `Practitioner.identifier` row at all (no GMC number field). Current
code maps `referrer_code`/`consultant_code` to a GMC-system identifier with a caveat that these may not
actually be GMC numbers. Worth flagging back to the spec owner — is `Practitioner.identifier` in scope or not?

---

## 7. Organization

| FHIR Element | Source | Status |
|---|---|---|
| `active` | Defaulted in IH → active | 🆕 Not currently set |
| `name` | `PADLOC.BASE_DESC` (WelshPAS **source-system lookup table**, not a payload field) | 🔴 **External lookup required.** Current code uses `referrer_org` payload field with a DHA-code fallback table. Spec now implies `Organization.name` should resolve via a `PADLOC` reference table keyed by HB/location code — this is not data we currently receive at all. |
| `telecom.system` / `telecom.value` | Defaulted `phone` / `PADLOC.HOSPITAL_TELEPHONE` | 🆕 New — external lookup required |
| `identifier:odsOrganisationCode` | Defaulted in IH → HB org code, e.g. `7A1` | 🟢 Roughly matches current DHA-code identifier approach, but should be a **default** derived from `system_id`, not the payload's `dhaCode` field |
| `address` (×5 rows) | "Pull data from WRDS" (Welsh Reference Data Service) | 🔴 **External lookup required** — new integration with WRDS needed, no current implementation |
| `partOf` | `PADLOC.PROVIDER_CODE` | 🆕 New — external lookup required |

---

## 8. Location

| FHIR Element | Source | Status |
|---|---|---|
| `status` | Defaulted in IH → active | 🆕 Not currently set |
| `name` | `PADLOC.LOCDESC` (source-system lookup) | 🔴 **Answers previous SPEC GAP but requires new lookup.** Previously flagged as "Huw to put stuff in payload" with no source; now clarified as a `PADLOC` table lookup, not a payload field. Current mapper uses free-text `referrer_location` — needs replacing with a lookup once `PADLOC` reference data is available. |
| `address` | *(no field — "can only be 1 line")* | 🟡 Constraint noted, no new source |
| `partOf` | `PADLOC.BASE_DESC` | 🆕 New — external lookup required, same table as `Organization.name` |

---

## 9. Encounter

| FHIR Element | Source | Status |
|---|---|---|
| `identifier.value` | `activityNotekey` | 🟢 **Answers previous SPEC GAP** |
| `statusHistory.status` / `.period` | Full `EncounterStatus` valueset: `planned\|arrived\|triaged\|in-progress\|onleave\|finished\|cancelled\|entered-in-error\|unknown` | 🆕 **Not modelled at all currently** — we only set a single `status`, not `statusHistory` |
| `class` | Much larger valueset: `ambulatory\|emergency\|field\|home health\|inpatient encounter\|inpatient acute\|inpatient non-acute\|observation encounter\|pre-admission\|short stay\|virtual` | 🔴 **Correction needed.** Current `_ENCOUNTER_CLASS` lookup only has `IMP`/`PRENC`/`AMB` (3 codes) — needs expanding to cover the full valueset, and needs a source field/rule to select the correct one (not currently specified in this sheet) |
| `diagnosis.condition` | *(no source)* | 🆕 Not modelled |
| `hospitalization.dischargeDisposition` | *(no source)* | 🆕 Not modelled |

---

## 10. Procedure

| FHIR Element | Source | Status |
|---|---|---|
| `identifier.value` | `PREMS_PROMS_FORMS.DESCRIPTION` (source-system lookup) | 🆕 **Answers previous SPEC GAP but requires new lookup** — not a payload field |
| `status` | Defaulted in IH → **`"unknown"`** | 🔴 **Correction.** Current code hardcodes `"completed"` with a `SPEC GAP` comment guessing at the value — spreadsheet now confirms the correct default is `unknown` |
| `code` | `eventPathway` | 🟢 Matches, same SNOMED caveat as ServiceRequest.code |
| `subject` | `nhsNumber` (confirms Patient reference is NHS-number based) | 🟢 Matches (already reference by Patient UUID) |
| `performed` | Defaulted → blank; relies on WelshPAS users adding it | 🟡 **Possible conflict** — current code builds `performedDateTime` from `appointmentDate`+`appointmentTime`. This sheet lists no WPAS source field at all for `Procedure.performed` (blank), implying it should default to absent rather than being derived from appointment fields. Needs clarifying — are appointment date/time a valid proxy, or should we stop populating this? |

---

## 11. Appointment

| FHIR Element | Source | Status |
|---|---|---|
| `identifier.value` | `activityNotekey` | 🟢 **Answers previous SPEC GAP** (same field as Encounter) |
| `status` | Full valueset listed: `planned\|arrived\|triaged\|in-progress\|onleave\|finished\|cancelled\|entered-in-error\|unknown` | ⚠️ **Likely a spreadsheet error** — this is the `EncounterStatus` valueset, not `AppointmentStatus` (which is `proposed\|pending\|booked\|arrived\|fulfilled\|cancelled\|noshow\|entered-in-error\|checked-in\|waitlist`). Flag back to spec owner rather than implementing as given. |
| `participant.actor.identifier.value` | `nhsNumber` | 🟢 Confirms Patient is the actor |
| `participant.status` | Business rule: `CONFIRM_APPT='Y'` → `accepted`, `='N'` → `declined`, `IS NULL` → `tentative` | 🟢 **Answers previous SPEC GAP with a concrete rule** — replaces the current hardcoded `"accepted"` |

---

## 12. Summary — Prioritised Work Items

### 🟢 Ready to implement now (concrete answers, no external dependencies) — ✅ ALL DONE
1. ✅ `Appointment.participant.status` — implemented the `CONFIRM_APPT` Y/N/null rule
2. ✅ `Procedure.status` — changed hardcoded default from `"completed"` to `"unknown"`
3. ✅ `Encounter.identifier` / `Appointment.identifier` — mapped from `activityNotekey`
4. ✅ `PractitionerRole.identifier.value` — mapped from `specialty_name`
5. ✅ `Patient.address.district` — mapped from `postalCounty`
6. ✅ Split `Patient` language handling — spoken language → new `contactPreference` extension, written language → `communication.language` (source field name for written language is a best guess pending confirmation — see item 9 below)
7. ✅ `ServiceRequest.status`/`.intent` — **confirmed already correct** (`"active"`/`"plan"`), no code change needed; the original assumption in this doc that these were hardcoded as `"Active"`/`"Planned"` was wrong

All 7 items implemented, tested (100/100 passing) and quality-gated (ruff/mypy/bandit clean) on
`feat/inthub/fhir-transformer-continuation`.

### 🟡 Needs a decision/confirmation before implementing
8. `MessageHeader.eventCoding` + new `reason` field — likely requires reworking `message_types.py` routing; need to confirm the `reason` qualifier model with spec owner
9. `Procedure.performed` — confirm whether deriving from `appointmentDate`/`appointmentTime` should continue or be dropped
10. `Appointment.status` valueset — flag likely copy/paste error back to spec owner
11. `PractitionerRole.organization` default (HB ODS code) vs current `referrer_org`-first logic — confirm precedence
12. `Practitioner.identifier` — confirm whether GMC-number mapping is still in scope
12a. `Patient.communication.language` source field — the exact WPAS field name for *written* language is not confirmed anywhere in the spreadsheet (only the label "preferred written language" is given); `preferred_written_language_code`/`written_language` are best-guess field names used in the current implementation pending confirmation

### 🔴 Needs new infrastructure (external lookups / reference data, bigger effort)
13. `Organization.name`/`.telecom`/`.partOf` and `Location.name`/`.partOf` — all depend on a new `PADLOC` reference table (not in the WPAS payload)
14. `Organization.address` — depends on WRDS (Welsh Reference Data Service) integration
15. `Encounter.class` — expand valueset from 3 codes to 11, need a mapping rule from source data
16. `Encounter.statusHistory`, `diagnosis.condition`, `hospitalization.dischargeDisposition` — new elements, no source field defined yet
17. `Patient.telecom` (4 fields), `maritalStatus`, `ethnicCategory`, `religion` extensions — fields exist in the model but marked "not yet sent" in WPAS payloads; build mappers defensively so they activate once WPAS starts sending them
18. `Procedure.identifier`/`ServiceRequest.code` SNOMED lookup — needs a coding/reference service, not just a field rename

---

*Document generated: 2026-09-08. Next step: work through section 12 items one at a time, starting with the
🟢 "ready now" list, confirming 🟡 decisions with the spec owner as we reach them.*
