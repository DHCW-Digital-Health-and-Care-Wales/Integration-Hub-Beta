"""Task mappers - `Bundle.entry[2]` and `Bundle.entry[3]` of a PSOM request.

Implements the two `Task` sections of the wiki Mapping Tables page. Both tasks
ask the patient to complete a questionnaire and differ only in their inputs:

* the EQ5D5L task carries the trigger event date, the laterality and the
  EQ-5D-5L questionnaire;
* the data entry task carries the laterality and the data entry questionnaire.
"""

from __future__ import annotations

from typing import Optional

from fhir.resources.R4B.codeableconcept import CodeableConcept
from fhir.resources.R4B.coding import Coding
from fhir.resources.R4B.task import Task, TaskInput

from ..fhir_constants import (
    COMPLETE_QUESTIONNAIRE_CODE,
    DATA_ENTRY_QUESTIONNAIRE,
    EQ5D5L_QUESTIONNAIRE,
    LATERALITY_NOT_APPLICABLE_CODE,
    LATERALITY_NOT_APPLICABLE_DISPLAY,
    PROMS_LATERALITY_CODE,
    PROMS_LATERALITY_DISPLAY,
    PROMS_LATERALITY_SYSTEM,
    QUESTIONNAIRE_INPUT_CODE,
    SDC_TEMP_SYSTEM,
    TASK_INPUT_TYPE_SYSTEM,
    TASK_INTENT,
    TASK_PROFILE,
    TASK_STATUS,
    TRIGGER_EVENT_DATE_CODE,
    TRIGGER_EVENT_DATE_DISPLAY,
    TRIGGER_EVENT_TYPE_SYSTEM,
)
from ..proms_parser import PromsMessage
from .mapping_utils import profile_meta


def _input_type(system: str, code: str, display: Optional[str] = None) -> CodeableConcept:
    """Build the `Task.input.type` CodeableConcept."""
    return CodeableConcept(coding=[Coding(system=system, code=code, display=display)])


def _trigger_event_date_input(message: PromsMessage) -> Optional[TaskInput]:
    """Build the PROMs trigger event date input.

    SPEC GAP: the wiki maps `UPI_EVENT_DATE` to `input.value` without stating the
    value type. It is emitted as a string so the WPAS value passes through
    unaltered, rather than being reformatted by a date parse.
    """
    event_date = message.get("UPI_EVENT_DATE", "upiEventDate")
    if not event_date:
        return None

    return TaskInput(
        type=_input_type(TASK_INPUT_TYPE_SYSTEM, TRIGGER_EVENT_DATE_CODE, TRIGGER_EVENT_DATE_DISPLAY),
        valueString=event_date,
    )


def _laterality_input() -> TaskInput:
    """Build the fixed "N/A" PROMs laterality input - WPAS carries no laterality."""
    return TaskInput(
        type=_input_type(TASK_INPUT_TYPE_SYSTEM, PROMS_LATERALITY_CODE, PROMS_LATERALITY_DISPLAY),
        valueCodeableConcept=CodeableConcept(
            coding=[
                Coding(
                    system=PROMS_LATERALITY_SYSTEM,
                    code=LATERALITY_NOT_APPLICABLE_CODE,
                    display=LATERALITY_NOT_APPLICABLE_DISPLAY,
                )
            ]
        ),
    )


def _questionnaire_input(questionnaire_url: str) -> TaskInput:
    """Build the input naming the questionnaire the patient must complete."""
    return TaskInput(
        type=_input_type(SDC_TEMP_SYSTEM, QUESTIONNAIRE_INPUT_CODE),
        valueCanonical=questionnaire_url,
    )


def _reason_code(message: PromsMessage) -> Optional[CodeableConcept]:
    """Build Task.reasonCode from the WPAS trigger event."""
    event_code = message.get("UPI_EVENT", "upiEvent")
    event_description = message.get("UPI_EVENT_DESC", "upiEventDesc")
    if not event_code and not event_description:
        return None

    return CodeableConcept(
        coding=[
            Coding(
                system=TRIGGER_EVENT_TYPE_SYSTEM,
                code=event_code or None,
                display=event_description or None,
            )
        ]
    )


def _base_task(message: PromsMessage, task_uuid: str) -> Task:
    """Build the parts both tasks share."""
    task = Task(
        id=task_uuid,
        meta=profile_meta(TASK_PROFILE),
        status=TASK_STATUS,
        intent=TASK_INTENT,
        code=CodeableConcept(
            coding=[Coding(system=SDC_TEMP_SYSTEM, code=COMPLETE_QUESTIONNAIRE_CODE)]
        ),
    )

    reason_code = _reason_code(message)
    if reason_code:
        task.reasonCode = reason_code

    return task


def map_eq5d5l_task(message: PromsMessage, task_uuid: str) -> Task:
    """Build the EQ-5D-5L questionnaire Task."""
    task = _base_task(message, task_uuid)

    inputs: list[TaskInput] = []
    trigger_event_date = _trigger_event_date_input(message)
    if trigger_event_date:
        inputs.append(trigger_event_date)
    inputs.append(_laterality_input())
    inputs.append(_questionnaire_input(EQ5D5L_QUESTIONNAIRE))

    task.input = inputs
    return task


def map_data_entry_task(message: PromsMessage, task_uuid: str) -> Task:
    """Build the data entry questionnaire Task.

    Unlike the EQ-5D-5L task this one carries no trigger event date input.
    """
    task = _base_task(message, task_uuid)
    task.input = [_laterality_input(), _questionnaire_input(DATA_ENTRY_QUESTIONNAIRE)]
    return task
