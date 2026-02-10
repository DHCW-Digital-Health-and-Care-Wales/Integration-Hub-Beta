from field_utils_lib import get_hl7_field_value
from hl7apy.core import Message

from ..date_of_death_transformer import transform_date_of_death
from ..segment_utils import copy_segment_fields_with_repetitions


def map_pid(original_msg: Message, new_msg: Message) -> tuple[str, str] | None:
    segment_names = [s.name for s in original_msg.children]
    if "PID" not in segment_names:
        return None

    pid_segment = original_msg.pid
    new_pid = new_msg.add_segment("PID")

    # Copy all PID fields except PID.29 (date of death), preserving repetitions.
    copy_segment_fields_with_repetitions(pid_segment, new_pid, "pid", start=1, end=28)
    copy_segment_fields_with_repetitions(pid_segment, new_pid, "pid", start=30, end=39)

    dod_field_value = getattr(pid_segment, "pid_29", None)

    if dod_field_value:
        original_dod = get_hl7_field_value(pid_segment, "pid_29.ts_1")
    else:
        original_dod = None

    if original_dod and original_dod.strip():
        transformed_dod = transform_date_of_death(original_dod)
        new_pid.pid_29.ts_1 = transformed_dod
        return (original_dod, transformed_dod)

    return None
