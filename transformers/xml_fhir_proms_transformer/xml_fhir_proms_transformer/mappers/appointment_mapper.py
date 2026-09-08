"""Appointment mapper — used for PREOP and CANCELLED bundle types."""

from __future__ import annotations

from typing import Optional

from fhir.resources.R4B.appointment import Appointment, AppointmentParticipant
from fhir.resources.R4B.codeableconcept import CodeableConcept
from fhir.resources.R4B.coding import Coding
from fhir.resources.R4B.identifier import Identifier
from fhir.resources.R4B.reference import Reference

from ..fhir_constants import APPOINTMENT_IDENTIFIER_SYSTEM, APPOINTMENT_PROFILE
from ..message_types import MessageType
from ..proms_parser import PromsMessage
from .mapping_utils import profile_meta, to_fhir_datetime


def _patient_participant_status(message: PromsMessage) -> str:
    """Derive Appointment.participant.status for the Patient participant.

    Confirmed business rule from the WelshPAS PROMs mapping spreadsheet:
      CONFIRM_APPT = 'Y' -> accepted
      CONFIRM_APPT = 'N' -> declined
      CONFIRM_APPT is null/absent -> tentative
    """
    confirm_appt = message.get("CONFIRM_APPT", "confirmAppt", "confirm_appt")
    normalised = confirm_appt.strip().upper()
    if normalised == "Y":
        return "accepted"
    if normalised == "N":
        return "declined"
    return "tentative"


def map_appointment(
    message: PromsMessage,
    appointment_uuid: str,
    patient_uuid: str,
    message_type: MessageType,
    practitioner_uuid: Optional[str] = None,
) -> Appointment:
    """Build the Appointment resource for PREOP or CANCELLED bundles."""
    participants = [
        AppointmentParticipant(
            actor=Reference(reference=f"urn:uuid:{patient_uuid}", type="Patient"),
            status=_patient_participant_status(message),
        )
    ]
    if practitioner_uuid:
        # SPEC GAP: no CONFIRM_APPT-equivalent rule is defined for the
        # practitioner participant. "accepted" is used as the default since
        # the practitioner is the appointment owner, not the invitee.
        participants.append(
            AppointmentParticipant(
                actor=Reference(reference=f"urn:uuid:{practitioner_uuid}", type="Practitioner"),
                status="accepted",
            )
        )

    appointment = Appointment(
        id=appointment_uuid,
        meta=profile_meta(APPOINTMENT_PROFILE),
        status=message_type.appointment_status or "booked",
        participant=participants,
    )

    # identifier — from activityNotekey (confirmed in the v2 WelshPAS mapping spreadsheet)
    activity_note_key = message.get("activityNotekey", "activity_note_key")
    if activity_note_key:
        appointment.identifier = [
            Identifier(system=APPOINTMENT_IDENTIFIER_SYSTEM, value=activity_note_key)
        ]

    # serviceType — from main_specialty_name
    service_type = message.get("main_specialty_name", "mainSpecialtyName", "specialty_name")
    if service_type:
        appointment.serviceType = [
            CodeableConcept(
                coding=[Coding(display=service_type)]
            )
        ]

    # start and end — from appointmentDate + appointmentTime
    # SPEC GAP: WPAS supplies a single appointment time with no duration or end time.
    # end is set equal to start as a placeholder until the spec owner confirms the
    # intended appointment duration or a dedicated end time field is added.
    date_raw = message.get("appointmentDate", "appointment_date")
    time_raw = message.get("appointmentTime", "appointment_time")
    combined = f"{date_raw} {time_raw}".strip() if (date_raw or time_raw) else None
    if combined:
        parsed = to_fhir_datetime(combined)
        if parsed:
            appointment.start = parsed
            appointment.end = parsed

    return appointment
