from field_utils_lib import copy_segment_fields_in_range, get_hl7_field_value
from hl7apy.core import Message

from ..datetime_transformer import transform_datetime


def map_msh(original_msg: Message, new_msg: Message) -> tuple[str, str] | None:
    # Intentional failure for DR testing: raise an error to simulate mapper bug
    raise RuntimeError("Simulated failure in MSH mapper for recovery testing")

    msh_segment = original_msg.msh
    new_msh = new_msg.msh

    copy_segment_fields_in_range(msh_segment, new_msh, "msh", start=3, end=21)

    created_datetime = get_hl7_field_value(msh_segment, "msh_7.ts_1")
    if created_datetime:
        transformed_datetime = transform_datetime(created_datetime)
        new_msh.msh_7.ts_1 = transformed_datetime
        return (created_datetime, transformed_datetime)

    return None
