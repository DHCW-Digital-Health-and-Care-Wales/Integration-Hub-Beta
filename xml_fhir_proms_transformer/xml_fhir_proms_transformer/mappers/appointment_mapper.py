"""Appointment mapper — used for PREOP and CANCELLED bundle types."""

from __future__ import annotations

from typing import Optional

from fhir.resources.R4B.appointment import Appointment, AppointmentParticipant
from fhir.resources.R4B.codeableconcept import CodeableConcept
from fhir.resources.R4B.coding import Coding
from fhir.resources.R4B.reference import Reference

from ..fhir_constants import APPOINTMENT_PROFILE
from ..message_types import MessageType
from ..proms_parser import PromsMessage
from .mapping_utils import profile_meta, to_fhir_datetime


def map_appointment(
    message: PromsMessage,
    appointment_uuid: str,
    patient_uuid: str,
    message_type: MessageType,
    practitioner_uuid: Optional[str] = None,
) -> Appointment:
    """Build the Appointment resource for PREOP or CANCELLED bundles.

    SPEC GAP: Appointment.participant.status — mapping spreadsheet does not
    specify the participant status code. Using "accepted" as the default for
    scheduled appointments. Confirm with spec owner.
    """
    participants = [
        AppointmentParticipant(
            actor=Reference(reference=f"urn:uuid:{patient_uuid}", type="Patient"),
            status="accepted",  # SPEC GAP: confirm correct participant status code
        )
    ]
    if practitioner_uuid:
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

    # serviceType — from main_specialty_name
    service_type = message.get("main_specialty_name", "mainSpecialtyName", "specialty_name")
    if service_type:
        appointment.serviceType = [
            CodeableConcept(
                coding=[Coding(display=service_type)]
            )
        ]

    # start and end — from appointmentDate + appointmentTime
    date_raw = message.get("appointmentDate", "appointment_date")
    time_raw = message.get("appointmentTime", "appointment_time")
    combined = f"{date_raw} {time_raw}".strip() if (date_raw or time_raw) else None
    if combined:
        parsed = to_fhir_datetime(combined)
        if parsed:
            appointment.start = parsed

    return appointment
