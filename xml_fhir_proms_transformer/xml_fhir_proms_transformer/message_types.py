"""Message type routing: WPAS eventCode -> FHIR bundle shape.

Derived from the WPAS PROMS Mapping spreadsheet (FHIR Review v1-0).  The actual
WPAS payload always has root element <PromsEventRequest>; routing is on the
<eventCode> child field, not the root tag.

    eventCode values -> bundle shape
    REFERRAL  -> Referral bundle  (MH, Patient, ServiceRequest, PractitionerRole, Practitioner, Org, Location)
    SURGERY   -> Procedure bundle (MH, Patient, Procedure, Practitioner, Org, Location)
    PREOP     -> Appointment bundle (MH, Patient, Appointment, Practitioner, Org, Location)
    INPATIENT -> Encounter bundle (MH, Patient, Encounter, Practitioner, Org, Location)
    CANCELLED -> Appointment Cancellation bundle (same shape as PREOP, status=cancelled)
    PREREAD   -> Encounter Pre-admission bundle (same shape as INPATIENT)

Each MessageType fixes the bundle entry order and carries the metadata needed by
the MessageHeader mapper (eventCoding code/display/definition).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .fhir_constants import (
    APPOINTMENT_CANCELLED_CODE,
    APPOINTMENT_CANCELLED_DISPLAY,
    APPOINTMENT_SCHEDULED_CODE,
    APPOINTMENT_SCHEDULED_DISPLAY,
    ENCOUNTER_CODE,
    ENCOUNTER_DISPLAY,
    PREADMISSION_CODE,
    PREADMISSION_DISPLAY,
    PROCEDURE_CODE,
    PROCEDURE_DISPLAY,
    REFERRAL_EVENT_CODE,
    REFERRAL_EVENT_DISPLAY,
    WPAS_EVENT_DEFINITION_BASE,
)

# Resource type labels used in entry_order tuples (informational only).
MESSAGE_HEADER = "MessageHeader"
PATIENT = "Patient"
SERVICE_REQUEST = "ServiceRequest"
PRACTITIONER_ROLE = "PractitionerRole"
PRACTITIONER = "Practitioner"
ORGANIZATION = "Organization"
LOCATION = "Location"
PROCEDURE = "Procedure"
ENCOUNTER = "Encounter"
APPOINTMENT = "Appointment"

# Common tail shared by most bundles.
_COMMON_TAIL = (PRACTITIONER, ORGANIZATION, LOCATION)


@dataclass(frozen=True)
class MessageType:
    """Bundle shape and FHIR metadata for one WPAS eventCode."""

    # The WPAS <eventCode> value that routes to this type.
    code: str
    # Human-readable name used in log messages.
    name: str
    # MessageHeader.eventCoding values.
    event_code: str
    event_display: str
    # Bundle entry order (positional, normative).
    entry_order: tuple[str, ...]
    # MessageHeader.definition - canonical MessageDefinition URL.
    definition: str = field(default="")
    # Whether this bundle type includes a PractitionerRole entry.
    has_practitioner_role: bool = False
    # The WPAS appointment status to set on Appointment.status (if applicable).
    appointment_status: str = ""


REFERRAL = MessageType(
    code="REFERRAL",
    name="REFERRAL",
    event_code=REFERRAL_EVENT_CODE,
    event_display=REFERRAL_EVENT_DISPLAY,
    entry_order=(MESSAGE_HEADER, PATIENT, SERVICE_REQUEST, PRACTITIONER_ROLE) + _COMMON_TAIL,
    definition=f"{WPAS_EVENT_DEFINITION_BASE}/referral",
    has_practitioner_role=True,
)

PROCEDURE_PERFORMED = MessageType(
    code="SURGERY",
    name="PROCEDURE_PERFORMED",
    event_code=PROCEDURE_CODE,
    event_display=PROCEDURE_DISPLAY,
    entry_order=(MESSAGE_HEADER, PATIENT, PROCEDURE) + _COMMON_TAIL,
    definition=f"{WPAS_EVENT_DEFINITION_BASE}/procedure",
)

APPOINTMENT_SCHEDULED = MessageType(
    code="PREOP",
    name="APPOINTMENT_SCHEDULED",
    event_code=APPOINTMENT_SCHEDULED_CODE,
    event_display=APPOINTMENT_SCHEDULED_DISPLAY,
    entry_order=(MESSAGE_HEADER, PATIENT, APPOINTMENT) + _COMMON_TAIL,
    definition=f"{WPAS_EVENT_DEFINITION_BASE}/appointment",
    appointment_status="booked",
)

INPATIENT_ADMISSION = MessageType(
    code="INPATIENT",
    name="INPATIENT_ADMISSION",
    event_code=ENCOUNTER_CODE,
    event_display=ENCOUNTER_DISPLAY,
    entry_order=(MESSAGE_HEADER, PATIENT, ENCOUNTER) + _COMMON_TAIL,
    definition=f"{WPAS_EVENT_DEFINITION_BASE}/encounter",
)

APPOINTMENT_CANCELLED = MessageType(
    code="CANCELLED",
    name="APPOINTMENT_CANCELLED",
    event_code=APPOINTMENT_CANCELLED_CODE,
    event_display=APPOINTMENT_CANCELLED_DISPLAY,
    entry_order=(MESSAGE_HEADER, PATIENT, APPOINTMENT) + _COMMON_TAIL,
    definition=f"{WPAS_EVENT_DEFINITION_BASE}/appointment-cancellation",
    appointment_status="cancelled",
)

PREADMISSION = MessageType(
    code="PREREAD",
    name="PREADMISSION",
    event_code=PREADMISSION_CODE,
    event_display=PREADMISSION_DISPLAY,
    entry_order=(MESSAGE_HEADER, PATIENT, ENCOUNTER) + _COMMON_TAIL,
    definition=f"{WPAS_EVENT_DEFINITION_BASE}/preadmission",
)

# Surgery performed maps to the same shape as Procedure.
SURGERY_PERFORMED = MessageType(
    code="SURGERY",
    name="SurgeryPerformed",
    event_code=PROCEDURE_CODE,
    event_display=PROCEDURE_DISPLAY,
    entry_order=(MESSAGE_HEADER, PATIENT, PROCEDURE) + _COMMON_TAIL,
    definition=f"{WPAS_EVENT_DEFINITION_BASE}/surgery",
)

# Outpatient visit uses Encounter shape.
OUTPATIENT_VISIT = MessageType(
    code="PREOP",
    name="OutpatientVisit",
    event_code=ENCOUNTER_CODE,
    event_display=ENCOUNTER_DISPLAY,
    entry_order=(MESSAGE_HEADER, PATIENT, ENCOUNTER) + _COMMON_TAIL,
    definition=f"{WPAS_EVENT_DEFINITION_BASE}/outpatient",
)

# Discharge maps to Encounter.
DISCHARGE = MessageType(
    code="SURGERY",
    name="Discharge",
    event_code=ENCOUNTER_CODE,
    event_display=ENCOUNTER_DISPLAY,
    entry_order=(MESSAGE_HEADER, PATIENT, ENCOUNTER) + _COMMON_TAIL,
    definition=f"{WPAS_EVENT_DEFINITION_BASE}/discharge",
)

# Primary routing table: one canonical MessageType per distinct eventCode.
# The spreadsheet defines multiple scenarios for SURGERY and PREOP but the
# eventCode alone cannot distinguish them — a single mapping is used per code
# until the specification owner confirms a disambiguation field.
# SPEC GAP: SURGERY is used for procedure-performed, surgery-performed and
# discharge. PREOP is used for appointment-scheduled and outpatient-visit.
# These are currently treated identically per code; raise with spec owner.
MESSAGE_TYPES_BY_CODE: dict[str, MessageType] = {
    "REFERRAL": REFERRAL,
    "SURGERY": PROCEDURE_PERFORMED,   # SPEC GAP: also maps surgery/discharge
    "PREOP": APPOINTMENT_SCHEDULED,   # SPEC GAP: also maps outpatient visit
    "INPATIENT": INPATIENT_ADMISSION,
    "CANCELLED": APPOINTMENT_CANCELLED,
    "PREREAD": PREADMISSION,
}


def resolve_message_type(event_code: str | None, root_tag: str = "") -> MessageType:
    """Select the MessageType for a payload.

    Resolution order:
      1. The <eventCode> field value (primary routing key in actual WPAS payloads).
      2. The XML root element name as a fallback (for future attribute-based format).

    Raises ValueError so process_message records a transformation failure rather
    than emitting a wrong bundle.
    """
    for candidate in (event_code, root_tag):
        if not candidate:
            continue
        key = candidate.strip().upper()
        resolved = MESSAGE_TYPES_BY_CODE.get(key)
        if resolved is not None:
            return resolved

    raise ValueError(
        f"Cannot route WPAS message: eventCode={event_code!r}, root={root_tag!r}. "
        f"Expected one of: {sorted(MESSAGE_TYPES_BY_CODE)}"
    )


# Legacy aliases kept for any remaining references during transition.
OUTPATIENT = APPOINTMENT_SCHEDULED
PATIENT_UPDATE = INPATIENT_ADMISSION
