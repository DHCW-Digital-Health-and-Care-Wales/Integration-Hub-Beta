from typing import Optional

from hl7apy.core import Message

from ..datetime_transformer import transform_datetime


def map_msh(original_msg: Message, new_msg: Message) -> Optional[tuple[str, str]]:

    msh_segment = original_msg.msh
    new_msh = new_msg.msh

    for i in range(3, 22):
        field_name = f"msh_{i}"
        try:
            original_field = getattr(msh_segment, field_name, None)
            if original_field and hasattr(original_field, "value") and original_field.value:
                setattr(new_msh, field_name, original_field.value)
        except Exception:
            pass

    created_datetime = msh_segment.msh_7.value if hasattr(msh_segment.msh_7, "value") else None
    if created_datetime:
        transformed_datetime = transform_datetime(created_datetime)
        new_msh.msh_7.value = transformed_datetime
        return (created_datetime, transformed_datetime)

    return None

