

from hl7apy.core import Message
from shared_libs.field_utils_lib.field_utils_lib.field_utils import copy_segment_fields_in_range, get_hl7_field_value


def map_evn(original_message: Message, new_message: Message) -> dict[str, str| None] | None:
    """EVN segment mapper function."""

    print("=" * 60 + "\nMapping EVN segment...\n" + "=" * 60)

    try:
        orig_evn_seg = original_message.evn
        new_evn_seg = new_message.evn
    except AttributeError:
        return None

    copy_segment_fields_in_range(
        source_segment= orig_evn_seg,
        target_segment= new_evn_seg,
        field_prefix= "evn",
        start=1,
        end=7
    )

    output_dict: dict[str, str | None] = {}

    output_dict["evn_1"] = get_hl7_field_value(orig_evn_seg, "evn_1") or None

    evn_2 = get_hl7_field_value(orig_evn_seg, "evn_2.ts_1")
    if evn_2:
        output_dict["evn_2"] = (
            get_hl7_field_value(orig_evn_seg, "evn_2.ts_1")
            or get_hl7_field_value(orig_evn_seg, "evn_2")
            or None
        )
    elif get_hl7_field_value(orig_evn_seg, "evn_2"):
        output_dict["evn_2"] = get_hl7_field_value(orig_evn_seg, "evn_2")

    output_dict["evn_3"] = get_hl7_field_value(orig_evn_seg, "evn_3") or None
    output_dict["evn_4"] = get_hl7_field_value(orig_evn_seg, "evn_5") or None
    output_dict["evn_5"] = get_hl7_field_value(orig_evn_seg, "evn_5") or None
    output_dict["evn_6"] = get_hl7_field_value(orig_evn_seg, "evn_6") or None
    output_dict["evn_7"] = get_hl7_field_value(orig_evn_seg, "evn_7") or None

    if output_dict:
        return output_dict
    return None
