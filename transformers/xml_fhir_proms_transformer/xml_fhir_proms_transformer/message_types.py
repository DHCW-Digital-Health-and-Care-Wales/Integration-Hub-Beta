"""Message type routing: WPAS eventCode -> FHIR bundle shape.

Derived from the WPAS PROMS Mapping spreadsheet (FHIR Review v1-0) and the
PROMS Scenarios spreadsheet. The actual WPAS payload always has root element
<PromsEventRequest>; routing is on the <eventCode> child field, not the root
tag.

    eventCode values -> bundle shape
    REFERRAL     -> Referral bundle    (MH, Patient, ServiceRequest, PractitionerRole, Practitioner, Org, Location)
    SURGERY-PROC -> Procedure bundle   (MH, Patient, Procedure, Practitioner, Org, Location)
    SURGERY-PERF -> Surgery bundle     (same shape as SURGERY-PROC)
    SURGERY-DN   -> Discharge bundle   (MH, Patient, Encounter, Practitioner, Org, Location)
    PREOP-AS     -> Appointment bundle (MH, Patient, Appointment, Practitioner, Org, Location)
    PREOP-VIS    -> Outpatient bundle  (MH, Patient, Encounter, Practitioner, Org, Location)
    PREOP-AR     -> Appointment Reschedule bundle (same shape as PREOP-AS)
    INPATIENT    -> Encounter bundle   (MH, Patient, Encounter, Practitioner, Org, Location)
    CANCELLED    -> Appointment Cancellation bundle (same shape as PREOP-AS, status=cancelled)
    PREREAD      -> Encounter Pre-admission bundle (same shape as INPATIENT)

TEMP: SURGERY-PROC/PERF/DN and PREOP-AS/VIS/AR are placeholder eventCode values
(PROMS Scenarios.xlsx "PROMS Message-TEMP" column) pending confirmation from
WPAS/the spec owner that WPAS will actually emit distinct codes per scenario.
The plain "SURGERY" and "PREOP" codes are kept as a legacy fallback, routed to
the original Procedure Performed / Appointment Scheduled scenarios, in case
WPAS has not yet switched to the new codes.

Each MessageType fixes the bundle entry order and carries the metadata needed by
the MessageHeader mapper (eventCoding code/display/definition).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .fhir_constants import (
    APPOINTMENT_CANCELLED_CODE,
    APPOINTMENT_CANCELLED_DISPLAY,
    APPOINTMENT_RESCHEDULE_CODE,
    APPOINTMENT_RESCHEDULE_DISPLAY,
    APPOINTMENT_SCHEDULED_CODE,
    APPOINTMENT_SCHEDULED_DISPLAY,
    DISCHARGE_CODE,
    DISCHARGE_DISPLAY,
    INPATIENT_CODE,
    INPATIENT_DISPLAY,
    OUTPATIENT_CODE,
    OUTPATIENT_DISPLAY,
    PREADMISSION_CODE,
    PREADMISSION_DISPLAY,
    PROCEDURE_CODE,
    PROCEDURE_DISPLAY,
    REFERRAL_EVENT_CODE,
    REFERRAL_EVENT_DISPLAY,
    SURGERY_PERFORMED_CODE,
    SURGERY_PERFORMED_DISPLAY,
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
    code="SURGERY-PROC",
    name="PROCEDURE_PERFORMED",
    event_code=PROCEDURE_CODE,
    event_display=PROCEDURE_DISPLAY,
    entry_order=(MESSAGE_HEADER, PATIENT, PROCEDURE) + _COMMON_TAIL,
    definition=f"{WPAS_EVENT_DEFINITION_BASE}/procedure",
)

APPOINTMENT_SCHEDULED = MessageType(
    code="PREOP-AS",
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
    event_code=INPATIENT_CODE,
    event_display=INPATIENT_DISPLAY,
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
    code="SURGERY-PERF",
    name="SURGERY_PERFORMED",
    event_code=SURGERY_PERFORMED_CODE,
    event_display=SURGERY_PERFORMED_DISPLAY,
    entry_order=(MESSAGE_HEADER, PATIENT, PROCEDURE) + _COMMON_TAIL,
    definition=f"{WPAS_EVENT_DEFINITION_BASE}/surgery",
)

# Outpatient visit uses Encounter shape.
OUTPATIENT_VISIT = MessageType(
    code="PREOP-VIS",
    name="OUTPATIENT_VISIT",
    event_code=OUTPATIENT_CODE,
    event_display=OUTPATIENT_DISPLAY,
    entry_order=(MESSAGE_HEADER, PATIENT, ENCOUNTER) + _COMMON_TAIL,
    definition=f"{WPAS_EVENT_DEFINITION_BASE}/outpatient",
)

# Discharge maps to Encounter.
DISCHARGE = MessageType(
    code="SURGERY-DN",
    name="DISCHARGE",
    event_code=DISCHARGE_CODE,
    event_display=DISCHARGE_DISPLAY,
    entry_order=(MESSAGE_HEADER, PATIENT, ENCOUNTER) + _COMMON_TAIL,
    definition=f"{WPAS_EVENT_DEFINITION_BASE}/discharge",
)

# Appointment reschedule uses the same shape as Appointment Scheduled; the
# Appointment.start/.end carry the updated date/time (see appointment_mapper).
APPOINTMENT_RESCHEDULE = MessageType(
    code="PREOP-AR",
    name="APPOINTMENT_RESCHEDULE",
    event_code=APPOINTMENT_RESCHEDULE_CODE,
    event_display=APPOINTMENT_RESCHEDULE_DISPLAY,
    entry_order=(MESSAGE_HEADER, PATIENT, APPOINTMENT) + _COMMON_TAIL,
    definition=f"{WPAS_EVENT_DEFINITION_BASE}/appointment-reschedule",
    appointment_status="booked",
)

# Primary routing table: one MessageType per distinct eventCode.
# TEMP: the SURGERY-*/PREOP-* codes are placeholders (see module docstring).
# The bare "SURGERY"/"PREOP" codes are kept as a legacy fallback, routed to
# the original Procedure Performed / Appointment Scheduled scenarios, for
# payloads that have not yet switched to the new disambiguated codes.
MESSAGE_TYPES_BY_CODE: dict[str, MessageType] = {
    "REFERRAL": REFERRAL,
    "SURGERY": PROCEDURE_PERFORMED,  # legacy fallback
    "SURGERY-PROC": PROCEDURE_PERFORMED,
    "SURGERY-PERF": SURGERY_PERFORMED,
    "SURGERY-DN": DISCHARGE,
    "PREOP": APPOINTMENT_SCHEDULED,  # legacy fallback
    "PREOP-AS": APPOINTMENT_SCHEDULED,
    "PREOP-VIS": OUTPATIENT_VISIT,
    "PREOP-AR": APPOINTMENT_RESCHEDULE,
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
PATIENT_UPDATE = INPATIENT_ADMISSION
