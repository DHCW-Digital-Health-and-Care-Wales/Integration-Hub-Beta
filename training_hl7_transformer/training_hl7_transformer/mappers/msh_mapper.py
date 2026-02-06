from field_utils_lib import copy_segment_fields_in_range, get_hl7_field_value
from hl7apy.core import Message

from training_hl7_transformer.datetime_transformer import transform_datetime_to_readable


def map_msh(original_msg: Message, new_msg: Message) -> tuple[str, str | None] | None:
    """MSH segment mapper function to copy fields and transform datetime."""

    print("=" * 60 + "\nMapping MSH segment...\n" + "=" * 60)

    msh_segment = original_msg.msh
    new_msh = new_msg.msh

    copy_segment_fields_in_range(msh_segment, new_msh, "msh", start=3, end=21)

    original_datetime = get_hl7_field_value(msh_segment, "msh_7.ts_1")
    transformed_datetime = None

    if original_datetime:
        transformed_datetime = transform_datetime_to_readable(original_datetime)
        new_msh.msh_7.ts_1.value = transformed_datetime # type: ignore
        return (original_datetime, transformed_datetime)

    return (original_datetime or "", transformed_datetime or "")
















