"""CarePlan mapper - `Bundle.entry[1]` of a PSOM request.

Implements the `CarePlan` rows of the wiki Mapping Tables page. The CarePlan
represents the PROMs pathway: it identifies the WPAS episode, categorises it by
specialty, and links the two questionnaire Tasks.
"""

from __future__ import annotations

from typing import Optional

from fhir.resources.R4B.careplan import CarePlan, CarePlanActivity
from fhir.resources.R4B.codeableconcept import CodeableConcept
from fhir.resources.R4B.coding import Coding
from fhir.resources.R4B.extension import Extension
from fhir.resources.R4B.identifier import Identifier
from fhir.resources.R4B.reference import Reference

from ..fhir_constants import (
    CARE_PLAN_INTENT,
    CARE_PLAN_PROFILE,
    CARE_PLAN_STATUS,
    DATA_ENTRY_TASK_DISPLAY,
    EQ5D5L_TASK_DISPLAY,
    LATERALITY_NOT_APPLICABLE_CODE,
    LATERALITY_NOT_APPLICABLE_DISPLAY,
    PATHWAY_LATERALITY_EXTENSION,
    PATHWAY_LATERALITY_SYSTEM,
    PATHWAY_TYPE_SYSTEM,
)
from ..proms_parser import PromsMessage
from ..reference_data import dha_code_name
from .mapping_utils import join_display, profile_meta, urn_uuid


def _pathway_laterality_extension() -> Extension:
    """Build the fixed "N/A" pathway laterality extension.

    WPAS carries no laterality, so the wiki hardcodes code 8 / "N/A".
    """
    return Extension(
        url=PATHWAY_LATERALITY_EXTENSION,
        valueCodeableConcept=CodeableConcept(
            coding=[
                Coding(
                    system=PATHWAY_LATERALITY_SYSTEM,
                    code=LATERALITY_NOT_APPLICABLE_CODE,
                    display=LATERALITY_NOT_APPLICABLE_DISPLAY,
                )
            ]
        ),
    )


def _identifier(message: PromsMessage, organization_uuid: Optional[str]) -> Optional[Identifier]:
    """Build the CarePlan identifier - the WPAS episode id, assigned by the health board.

    SPEC GAP: the wiki maps `identifier.system` directly from `SYSTEM_ID`, which
    is a numeric health board code rather than a URI. It is emitted verbatim to
    match the Fiorano output; raise with the spec owner if a URI is expected.
    """
    unique_id = message.get("UNIQUE_ID", "uniqueId")
    if not unique_id:
        return None

    identifier = Identifier(
        system=message.get("SYSTEM_ID", "system_id", "systemId") or None,
        value=unique_id,
    )

    dha_code = message.get("DHA_CODE", "dhaCode")
    if organization_uuid or dha_code:
        identifier.assigner = Reference(
            reference=urn_uuid(organization_uuid) if organization_uuid else None,
            display=dha_code_name(dha_code),
        )

    return identifier


def _category(message: PromsMessage) -> Optional[list[CodeableConcept]]:
    """Build CarePlan.category - the specialty that owns the pathway."""
    specialty_code = message.get("SPEC", "spec")
    specialty_name = message.get("SPEC_NAME", "specName")
    if not specialty_code and not specialty_name:
        return None

    return [
        CodeableConcept(
            coding=[
                Coding(
                    system=PATHWAY_TYPE_SYSTEM,
                    code=specialty_code or None,
                    display=specialty_name or None,
                )
            ]
        )
    ]


def _task_activities(eq5d5l_task_uuid: str, data_entry_task_uuid: str) -> list[CarePlanActivity]:
    """Link the two questionnaire Tasks as CarePlan activities."""
    return [
        CarePlanActivity(
            reference=Reference(
                reference=urn_uuid(eq5d5l_task_uuid),
                type="Task",
                display=EQ5D5L_TASK_DISPLAY,
            )
        ),
        CarePlanActivity(
            reference=Reference(
                reference=urn_uuid(data_entry_task_uuid),
                type="Task",
                display=DATA_ENTRY_TASK_DISPLAY,
            )
        ),
    ]


def map_care_plan(
    message: PromsMessage,
    care_plan_uuid: str,
    patient_uuid: str,
    eq5d5l_task_uuid: str,
    data_entry_task_uuid: str,
    practitioner_uuid: Optional[str] = None,
    organization_uuid: Optional[str] = None,
) -> CarePlan:
    """Build the CarePlan resource."""
    care_plan = CarePlan(
        id=care_plan_uuid,
        meta=profile_meta(CARE_PLAN_PROFILE),
        status=CARE_PLAN_STATUS,
        intent=CARE_PLAN_INTENT,
        subject=Reference(
            reference=urn_uuid(patient_uuid),
            type="Patient",
            display=join_display(
                message.get("FORENAME", "patientFirstname", "forename"),
                message.get("SURNAME", "patientSurname", "surname"),
            ),
        ),
    )

    care_plan.extension = [_pathway_laterality_extension()]

    identifier = _identifier(message, organization_uuid)
    if identifier:
        care_plan.identifier = [identifier]

    category = _category(message)
    if category:
        care_plan.category = category

    if practitioner_uuid:
        care_plan.author = Reference(
            reference=urn_uuid(practitioner_uuid),
            type="Practitioner",
            display=join_display(message.get("CONS_NAME", "clinicianName"), message.get("CONS_GMC")),
        )

    care_plan.activity = _task_activities(eq5d5l_task_uuid, data_entry_task_uuid)

    return care_plan
