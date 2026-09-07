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
PATIENT_PROFILE = "https://fhir.nhs.wales/StructureDefinition/DataStandardsWales-Patient"
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

PROCEDURE_CODE = "SURGERY"
PROCEDURE_DISPLAY = "Procedure Performed"

APPOINTMENT_SCHEDULED_CODE = "PREOP"
APPOINTMENT_SCHEDULED_DISPLAY = "Appointment Scheduled"

INPATIENT_CODE = "INPATIENT"
INPATIENT_DISPLAY = "Inpatient Admission"

APPOINTMENT_CANCELLED_CODE = "CANCELLED"
APPOINTMENT_CANCELLED_DISPLAY = "Appointment Cancellation"

PREADMISSION_CODE = "PREREAD"
PREADMISSION_DISPLAY = "Pre-admission Notification"

# --- MessageHeader destination (Promptly Collect) ---------------------------
PROMPTLY_COLLECT_DESTINATION_NAME = "FHIR Promptly Collect"
PROMPTLY_COLLECT_ENDPOINT = "https://collect.promptlyhealth.com/fhir"

# --- Identifier systems -----------------------------------------------------
NHS_NUMBER_SYSTEM = "https://fhir.nhs.uk/Id/nhs-number"
ODS_ORGANISATION_CODE_SYSTEM = "https://fhir.nhs.uk/Id/ods-organization-code"
GMC_NUMBER_SYSTEM = "https://fhir.hl7.org.uk/Id/gmc-number"
LOCATION_IDENTIFIER_SYSTEM = "https://fhir.nhs.wales/Id/wrts-location-identifier"
SERVICE_REQUEST_IDENTIFIER_SYSTEM = (
    "https://wpas-integration-ig.tools.labs.promptly.health/id/wpas-servicerequest"
)
PRACTITIONER_ROLE_IDENTIFIER_SYSTEM = (
    "https://wpas-integration-ig.tools.labs.promptly.health/id/wpas-practitionerrole"
)

# --- NHS Number verification -------------------------------------------------
NHS_NUMBER_VERIFICATION_EXTENSION = (
    "https://fhir.hl7.org.uk/StructureDefinition/Extension-UKCore-NHSNumberVerificationStatus"
)
NHS_NUMBER_VERIFICATION_SYSTEM = (
    "https://fhir.hl7.org.uk/CodeSystem/UKCore-NHSNumberVerificationStatusWales"
)

# --- Patient language -------------------------------------------------------
HUMAN_LANGUAGE_SYSTEM = "https://fhir.hl7.org.uk/CodeSystem/UKCore-HumanLanguage"

# --- Encounter class coding (v3 ActCode) ------------------------------------
ENCOUNTER_CLASS_SYSTEM = "http://terminology.hl7.org/CodeSystem/v3-ActCode"
ENCOUNTER_CLASS_INPATIENT_CODE = "IMP"
ENCOUNTER_CLASS_INPATIENT_DISPLAY = "Inpatient encounter"
ENCOUNTER_CLASS_PREADMISSION_CODE = "PRENC"
ENCOUNTER_CLASS_PREADMISSION_DISPLAY = "Pre-admission"
ENCOUNTER_CLASS_AMBULATORY_CODE = "AMB"
ENCOUNTER_CLASS_AMBULATORY_DISPLAY = "Ambulatory"

# --- Procedure --------------------------------------------------------------
# SPEC GAP: hardcoded value in spreadsheet is "Yes" which is not a valid
# FHIR EventStatus code. Using "completed" pending confirmation from spec owner.
PROCEDURE_STATUS_DEFAULT = "completed"

# --- Appointment ------------------------------------------------------------
# SPEC GAP: participant.status is 1..1 required. Using "accepted" pending
# confirmation from spec owner.
APPOINTMENT_PARTICIPANT_STATUS_DEFAULT = "accepted"

# --- ServiceRequest ---------------------------------------------------------
SERVICE_REQUEST_STATUS = "active"
SERVICE_REQUEST_INTENT = "plan"

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

# Aliases for Encounter event coding (INPATIENT / PREREAD share the encounter shape)
ENCOUNTER_CODE = INPATIENT_CODE
ENCOUNTER_DISPLAY = INPATIENT_DISPLAY
