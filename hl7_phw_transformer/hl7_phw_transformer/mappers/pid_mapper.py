from typing import Optional

from hl7apy.core import Message

from ..date_of_death_transformer import transform_date_of_death


def map_pid(original_msg: Message, new_msg: Message) -> Optional[tuple[str, str]]:

    pid_segment = getattr(original_msg, "pid", None)
    if not pid_segment:
        return None

    new_pid = new_msg.add_segment("PID")

    for i in range(1, 40):
        field_name = f"pid_{i}"
        try:
            original_field = getattr(pid_segment, field_name, None)
            if original_field and hasattr(original_field, "value") and original_field.value:
                setattr(new_pid, field_name, original_field.value)
        except Exception:
            pass

    dod_field = getattr(pid_segment, "pid_29", None)
    original_dod = getattr(dod_field, "value", None) if dod_field else None

    if original_dod is not None and original_dod:
        transformed_dod = transform_date_of_death(original_dod)
        new_pid.pid_29.value = transformed_dod
        return (original_dod, transformed_dod)

    return None

