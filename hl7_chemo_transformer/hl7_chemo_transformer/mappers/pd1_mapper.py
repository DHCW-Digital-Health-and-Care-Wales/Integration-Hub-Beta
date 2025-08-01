from hl7apy.core import Message

from ..utils.field_utils import set_nested_field


def map_pd1(original_hl7_message: Message, new_message: Message) -> None:
    original_pd1 = getattr(original_hl7_message, "pd1", None)
    if original_pd1 is None:
        return  # No PD1 segment

    pd1_3_fields = ["xon_1", "xon_3", "xon_4", "xon_5", "xon_7", "xon_9"]
    for field in pd1_3_fields:
        set_nested_field(original_pd1, new_message.pd1, f"pd1_3.{field}")

    pd1_4_fields = ["xcn_1", "xcn_3", "xcn_4", "xcn_6"]
    for field in pd1_4_fields:
        set_nested_field(original_pd1, new_message.pd1, f"pd1_4.{field}")

    set_nested_field(original_pd1, new_message.pd1, "pd1_3.xon_6.hd_1")
    set_nested_field(original_pd1, new_message.pd1, "pd1_3.xon_8.hd_1")
    set_nested_field(original_pd1, new_message.pd1, "pd1_4.xcn_2.fn_1")
