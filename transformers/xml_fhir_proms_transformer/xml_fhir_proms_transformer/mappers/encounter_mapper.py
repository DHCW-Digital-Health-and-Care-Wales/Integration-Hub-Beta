"""Encounter mapper — used for INPATIENT and PREREAD bundle types."""

from __future__ import annotations

from fhir.resources.R4B.coding import Coding
from fhir.resources.R4B.encounter import Encounter
from fhir.resources.R4B.reference import Reference

from ..fhir_constants import (
    ENCOUNTER_CLASS_SYSTEM,
    ENCOUNTER_PROFILE,
)
from ..message_types import MessageType
from ..proms_parser import PromsMessage
from .mapping_utils import profile_meta

# Map MessageType.name → (class code, class display, encounter status)
_ENCOUNTER_CLASS: dict[str, tuple[str, str, str]] = {
    "INPATIENT_ADMISSION": ("IMP", "inpatient encounter", "in-progress"),
    "PREADMISSION": ("PRENC", "pre-admission", "planned"),
}
_DEFAULT_CLASS = ("AMB", "ambulatory", "in-progress")


def map_encounter(
    message: PromsMessage,
    encounter_uuid: str,
    patient_uuid: str,
    message_type: MessageType,
) -> Encounter:
    """Build the Encounter resource for INPATIENT or PREREAD bundles."""
    type_name = message_type.name
    class_code, class_display, status = _ENCOUNTER_CLASS.get(type_name, _DEFAULT_CLASS)

    # `class` is a reserved Python keyword so we pass it by alias via **{}.
    # class_fhir is required at construction time — pydantic validates on __init__.
    class_coding = Coding(system=ENCOUNTER_CLASS_SYSTEM, code=class_code, display=class_display)
    encounter = Encounter(
        **{
            "id": encounter_uuid,
            "meta": profile_meta(ENCOUNTER_PROFILE),
            "status": status,
            "class": class_coding,
            "subject": Reference(reference=f"urn:uuid:{patient_uuid}", type="Patient"),
        }
    )
    return encounter
