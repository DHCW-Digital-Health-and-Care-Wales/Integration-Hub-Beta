"""Static values required by the WPAS -> PROMS FHIR mapping.

All values are derived from the WPAS PROMS Mapping - FHIR Review spreadsheet
(By Profile v1-0) and the PROMS Scenarios spreadsheet. The target implementation
guide is the Promptly Health WPAS Integration IG combined with Data Standards
Wales profiles for Patient, Practitioner and Organization.

Target FHIR version is R4B.
"""

from __future__ import annotations

# --- Profiles ---------------------------------------------------------------
MESSAGE_HEADER_PROFILE = "https://fhir.promptly.health/wpas/StructureDefinition/wpas-messageheader"
# SPEC GAP: reviewer flagged the above as incorrect — awaiting confirmed NHS Wales URL
PATIENT_PROFILE = "https://fhir.nhs.wales/StructureDefinition/wpas-patient"
PRACTITIONER_PROFILE = "https://fhir.nhs.wales/StructureDefinition/DataStandardsWales-Practitioner"
PRACTITIONER_ROLE_PROFILE = "https://fhir.nhs.wales/StructureDefinition/DataStandardsWales-PractitionerRole"
ORGANIZATION_PROFILE = "https://fhir.nhs.wales/StructureDefinition/DataStandardsWales-Organization"
LOCATION_PROFILE = "https://fhir.nhs.wales/StructureDefinition/DataStandardsWales-Location"
SERVICE_REQUEST_PROFILE = "https://fhir.hl7.org.uk/StructureDefinition/UKCore-ServiceRequest"
ENCOUNTER_PROFILE = "https://fhir.hl7.org.uk/StructureDefinition/UKCore-Encounter"
PROCEDURE_PROFILE = "https://fhir.hl7.org.uk/StructureDefinition/UKCore-Procedure"
APPOINTMENT_PROFILE = "https://fhir.hl7.org.uk/StructureDefinition/UKCore-Appointment"

# --- MessageHeader event coding ---------------------------------------------
WPAS_EVENT_SYSTEM = "https://fhir.promptly.health/wpas/CodeSystem/wpas-event-codes"
WPAS_EVENT_DEFINITION_BASE = "https://fhir.promptly.health/wpas/MessageDefinition/wpas"

REFERRAL_EVENT_CODE = "REFERRAL"
REFERRAL_EVENT_DISPLAY = "Patient Referral"

# TEMP: placeholder eventCode values pending WPAS/spec owner confirmation.
# SURGERY and PREOP were previously ambiguous (each covered 2-3 distinct
# scenarios per the PROMS Scenarios / WPAS PROMS Mapping spreadsheets). These
# suffixed codes disambiguate them; see PROMS Scenarios.xlsx "PROMS
# Message-TEMP" column.
PROCEDURE_CODE = "SURGERY-PROC"
PROCEDURE_DISPLAY = "Procedure Performed"

SURGERY_PERFORMED_CODE = "SURGERY-PERF"
SURGERY_PERFORMED_DISPLAY = "Surgery Performed"

DISCHARGE_CODE = "SURGERY-DN"
DISCHARGE_DISPLAY = "Discharge Notification"

APPOINTMENT_SCHEDULED_CODE = "PREOP-AS"
APPOINTMENT_SCHEDULED_DISPLAY = "Appointment Scheduled"

OUTPATIENT_CODE = "PREOP-VIS"
OUTPATIENT_DISPLAY = "Outpatient Visit"

APPOINTMENT_RESCHEDULE_CODE = "PREOP-AR"
APPOINTMENT_RESCHEDULE_DISPLAY = "Appointment Reschedule"

INPATIENT_CODE = "INPATIENT"
INPATIENT_DISPLAY = "Inpatient Admission"

APPOINTMENT_CANCELLED_CODE = "CANCELLED"
APPOINTMENT_CANCELLED_DISPLAY = "Appointment Cancellation"

PREADMISSION_CODE = "PREREAD"
PREADMISSION_DISPLAY = "Pre-admission Notification"

# --- MessageHeader destination (Promptly Collect) ---------------------------
PROMPTLY_COLLECT_DESTINATION_NAME = "FHIR Promptly Collect"
# The destination endpoint differs per environment, so it is overridable via the
# PROMPTLY_DESTINATION_ENDPOINT env var; this default is the Promptly staging endpoint.
PROMPTLY_DESTINATION_ENDPOINT_ENV_VAR = "PROMPTLY_DESTINATION_ENDPOINT"
PROMPTLY_COLLECT_ENDPOINT = "https://wpas-fhir.stg.labs.promptly.health/fhir/r4/$process-message"

# MessageHeader.source.endpoint = base + "/" + WPAS system_id
WPAS_SOURCE_ENDPOINT_BASE = "https://fhir.nhs.uk/source-system/wpas"

# --- Identifier systems -----------------------------------------------------
NHS_NUMBER_SYSTEM = "https://fhir.nhs.uk/Id/nhs-number"
ODS_ORGANISATION_CODE_SYSTEM = "https://fhir.nhs.uk/Id/ods-organization-code"
GMC_NUMBER_SYSTEM = "https://fhir.hl7.org.uk/Id/gmc-number"
WPAS_PRACTITIONER_SYSTEM = "https://fhir.nhs.wales/Id/wpas-practitioner"
LOCATION_IDENTIFIER_SYSTEM = "https://fhir.nhs.wales/Id/wrts-location-identifier"
SERVICE_REQUEST_IDENTIFIER_SYSTEM = "https://fhir.nhs.wales/Id/wpas-servicerequest"
# Referral PractitionerRoles are identified by the referrer's GMC number; every
# other bundle uses the WPAS practitioner-role system.
PRACTITIONER_ROLE_IDENTIFIER_SYSTEM = "https://fhir.nhs.wales/Id/wpas-practitioner-role"
PRACTITIONER_ROLE_REFERRAL_IDENTIFIER_SYSTEM = GMC_NUMBER_SYSTEM
ENCOUNTER_IDENTIFIER_SYSTEM = (
    "https://wpas-integration-ig.tools.labs.promptly.health/id/wpas-encounter"
)
APPOINTMENT_IDENTIFIER_SYSTEM = (
    "https://wpas-integration-ig.tools.labs.promptly.health/id/wpas-appointment"
)

# --- NHS Number verification -------------------------------------------------
NHS_NUMBER_VERIFICATION_EXTENSION = (
    "https://fhir.hl7.org.uk/StructureDefinition/Extension-UKCore-NHSNumberVerificationStatus"
)
NHS_NUMBER_VERIFICATION_SYSTEM = (
    "https://fhir.hl7.org.uk/CodeSystem/UKCore-NHSNumberVerificationStatusWales"
)

# --- Patient language / ethnicity / telecom ----------------------------------
# Spoken language maps to Patient.communication.language (Amy_Questions mapping).
SPOKEN_LANGUAGE_SYSTEM = "https://fhir.nhs.wales/CodeSystem/wpas-spoken-language"
ETHNIC_CATEGORY_EXTENSION = "https://fhir.hl7.org.uk/StructureDefinition/Extension-UKCore-EthnicCategory"
ETHNICITY_SYSTEM = "https://fhir.nhs.wales/CodeSystem/wpas-ethnicity"

# --- Encounter class coding (v3 ActCode) ------------------------------------
ENCOUNTER_CLASS_SYSTEM = "http://terminology.hl7.org/CodeSystem/v3-ActCode"
ENCOUNTER_CLASS_INPATIENT_CODE = "IMP"
ENCOUNTER_CLASS_INPATIENT_DISPLAY = "Inpatient encounter"
ENCOUNTER_CLASS_PREADMISSION_CODE = "PRENC"
ENCOUNTER_CLASS_PREADMISSION_DISPLAY = "Pre-admission"
ENCOUNTER_CLASS_AMBULATORY_CODE = "AMB"
ENCOUNTER_CLASS_AMBULATORY_DISPLAY = "Ambulatory"
# TEMP: placeholder pending WPAS/spec owner confirmation (WPAS PROMS Mapping -
# Final.xlsx, Encounter sheet, red/bold additions). The v3 ActCode
# EncounterClass value set has no dedicated "discharge" code — discharge is
# not a distinct encounter class, it is the same (e.g. inpatient) encounter
# reaching status="finished" (optionally with hospitalization.
# dischargeDisposition, not yet mapped). Reusing the valid IMP code here keeps
# the bundle terminology-valid; revisit once the spec owner confirms whether
# discharges should also carry a dischargeDisposition or a different class.
ENCOUNTER_CLASS_DISCHARGE_CODE = ENCOUNTER_CLASS_INPATIENT_CODE
ENCOUNTER_CLASS_DISCHARGE_DISPLAY = ENCOUNTER_CLASS_INPATIENT_DISPLAY

# --- Procedure --------------------------------------------------------------
# Confirmed by the WPAS PROMS Mapping - FHIR Review (By Profile v1-0 - Final)
# spreadsheet: Procedure.status is hardcoded to "Completed" once the
# procedure/surgery has taken place. This supersedes the earlier
# PROMS_FHIR_Mapping_Analysis_v2.md recommendation of "unknown", which was
# based on a different, now-superseded spreadsheet.
PROCEDURE_STATUS_DEFAULT = "completed"

# --- Appointment ------------------------------------------------------------
# SPEC GAP: participant.status is 1..1 required. Using "accepted" pending
# confirmation from spec owner.
APPOINTMENT_PARTICIPANT_STATUS_DEFAULT = "accepted"

# --- ServiceRequest ---------------------------------------------------------
SERVICE_REQUEST_STATUS = "active"
SERVICE_REQUEST_INTENT = "order"
# code = the WPAS event code (REFERRAL); reasonCode = the clinical pathway (eventPathway).
SERVICE_REQUEST_CODE_SYSTEM = "https://fhir.nhs.wales/CodeSystem/proms-event"
SERVICE_REQUEST_CODE_DISPLAY = "Referral"
SERVICE_REQUEST_REASON_SYSTEM = "https://fhir.nhs.wales/CodeSystem/wpas-event-pathway"

# --- Legacy PSOM constants kept to avoid breaking any surviving references ---
# These are no longer emitted in any bundle but are retained until all
# references in tests/docs have been cleaned up.
PSOM_REQUEST_CODE = "psom-request"
PSOM_REQUEST_DISPLAY = "PSOM request"
PATIENT_UPDATE_CODE = "patient-update"
PATIENT_UPDATE_DISPLAY = "Patient update"
PSOM_REQUEST_DEFINITION = "https://fhir.nhs.wales/MessageDefinition/DataStandardsWales-PSOM-request"
PATIENT_UPDATE_DEFINITION = "https://fhir.nhs.wales/MessageDefinition/DataStandardsWales-PSOM-PatientUpdate"
MESSAGE_EVENT_SYSTEM = WPAS_EVENT_SYSTEM  # alias
