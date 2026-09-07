"""Procedure mapper — used for the SURGERY bundle type."""

from __future__ import annotations

from fhir.resources.R4B.codeableconcept import CodeableConcept
from fhir.resources.R4B.coding import Coding
from fhir.resources.R4B.procedure import Procedure
from fhir.resources.R4B.reference import Reference

from ..fhir_constants import PROCEDURE_PROFILE
from ..proms_parser import PromsMessage
from .mapping_utils import profile_meta, to_fhir_datetime


def map_procedure(
    message: PromsMessage,
    procedure_uuid: str,
    patient_uuid: str,
) -> Procedure:
    """Build the Procedure resource for a Surgery bundle.

    SPEC GAP: Procedure.status — the mapping spreadsheet has "Yes" (invalid FHIR).
    "completed" is used as the only semantically valid code for a recorded surgery.
    Confirm with spec owner.
    """
    procedure = Procedure(
        id=procedure_uuid,
        meta=profile_meta(PROCEDURE_PROFILE),
        status="completed",  # SPEC GAP: spreadsheet says "Yes" — not a valid code
        subject=Reference(reference=f"urn:uuid:{patient_uuid}", type="Patient"),
    )

    # code — from eventPathway
    event_pathway = message.get("eventPathway", "event_pathway")
    if event_pathway:
        procedure.code = CodeableConcept(
            coding=[
                Coding(
                    code=event_pathway,
                    display="Procedure performed",
                )
            ]
        )

    # performedDateTime — from appointmentDate + appointmentTime
    date_raw = message.get("appointmentDate", "appointment_date")
    time_raw = message.get("appointmentTime", "appointment_time")
    combined = f"{date_raw} {time_raw}".strip() if (date_raw or time_raw) else None
    if combined:
        parsed = to_fhir_datetime(combined)
        if parsed:
            procedure.performedDateTime = parsed

    return procedure
