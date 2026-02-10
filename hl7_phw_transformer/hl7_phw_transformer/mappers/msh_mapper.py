from field_utils_lib import get_hl7_field_value
from hl7apy.core import Message

from ..datetime_transformer import transform_datetime
from ..segment_utils import copy_segment_fields_with_repetitions


def map_msh(original_msg: Message, new_msg: Message) -> tuple[str, str] | None:
    msh_segment = original_msg.msh
    new_msh = new_msg.msh

    # Copy all MSH fields except MSH-7 (Date/Time of Message), which is handled
    # explicitly below to avoid overwriting the auto-populated timestamp on the
    # new message when the original does not carry a value.
    copy_segment_fields_with_repetitions(msh_segment, new_msh, "msh", start=3, end=6)
    copy_segment_fields_with_repetitions(msh_segment, new_msh, "msh", start=8, end=21)

    try:
        new_msh.msh_12[0].value = msh_segment.msh_12[0].value
    except Exception:
        pass

    created_datetime = get_hl7_field_value(msh_segment, "msh_7.ts_1")
    if created_datetime:
        transformed_datetime = transform_datetime(created_datetime)
        new_msh.msh_7.ts_1 = transformed_datetime
        return (created_datetime, transformed_datetime)

    return None
