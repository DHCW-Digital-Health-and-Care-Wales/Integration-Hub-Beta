"""Procedure mapper — used for the SURGERY-PROC and SURGERY-PERF bundle types."""

from __future__ import annotations

from fhir.resources.R4B.codeableconcept import CodeableConcept
from fhir.resources.R4B.coding import Coding
from fhir.resources.R4B.procedure import Procedure
from fhir.resources.R4B.reference import Reference

from ..fhir_constants import PROCEDURE_PROFILE, PROCEDURE_STATUS_DEFAULT
from ..proms_parser import PromsMessage
from .mapping_utils import profile_meta, to_fhir_datetime


def map_procedure(
    message: PromsMessage,
    procedure_uuid: str,
    patient_uuid: str,
) -> Procedure:
    """Build the Procedure resource for a Procedure/Surgery bundle.

    Procedure.status is hardcoded to "completed" - confirmed by the WPAS PROMS
    Mapping - FHIR Review (By Profile v1-0 - Final) spreadsheet: "Set it to
    completed once the procedure/surgery has taken place". This supersedes the
    earlier PROMS_FHIR_Mapping_Analysis_v2.md recommendation of "unknown",
    which was based on a different, now-superseded spreadsheet.
    """
    procedure = Procedure(
        id=procedure_uuid,
        meta=profile_meta(PROCEDURE_PROFILE),
        status=PROCEDURE_STATUS_DEFAULT,
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
