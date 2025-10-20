from field_utils_lib import copy_segment_fields_in_range
from hl7apy.core import Message

from ..date_of_death_transformer import transform_date_of_death


def map_pid(original_msg: Message, new_msg: Message) -> tuple[str, str] | None:
    pid_segment = getattr(original_msg, "pid", None)
    if not pid_segment:
        return None

    new_pid = new_msg.add_segment("PID")

    copy_segment_fields_in_range(pid_segment, new_pid, "pid", start=1, end=39)

    dod_field_value = getattr(pid_segment, "pid_29", None)
    original_dod = getattr(dod_field_value, "value", None) if dod_field_value else None

    if original_dod is not None and original_dod:
        transformed_dod = transform_date_of_death(original_dod)
        new_pid.pid_29.value = transformed_dod
        return (original_dod, transformed_dod)

    return None
