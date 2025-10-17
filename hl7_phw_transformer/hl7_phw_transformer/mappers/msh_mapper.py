from field_utils_lib import get_hl7_field_value, set_nested_field
from hl7apy.core import Message

from ..datetime_transformer import transform_datetime


def map_msh(original_msg: Message, new_msg: Message) -> tuple[str, str] | None:

    msh_segment = original_msg.msh
    new_msh = new_msg.msh

    # Copy MSH fields 3-21 using set_nested_field
    for i in range(3, 22):
        field_name = f"msh_{i}"
        set_nested_field(msh_segment, new_msh, field_name)

    created_datetime = get_hl7_field_value(msh_segment, "msh_7.ts_1")
    if created_datetime:
        transformed_datetime = transform_datetime(created_datetime)
        new_msh.msh_7.ts_1 = transformed_datetime
        return (created_datetime, transformed_datetime)

    return None

