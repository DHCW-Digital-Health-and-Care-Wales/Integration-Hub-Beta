from hl7apy.core import Message

from ..utils.field_utils import set_nested_field


def map_pd1(original_hl7_message: Message, new_message: Message) -> None:
    original_pd1 = getattr(original_hl7_message, "pd1", None)
    if original_pd1 is None:
        return  # No PD1 segment

    set_nested_field(original_pd1, new_message.pd1, "pd1_3", "xon_1")
    set_nested_field(original_pd1, new_message.pd1, "pd1_3", "xon_3")
    set_nested_field(original_pd1, new_message.pd1, "pd1_3", "xon_4")
    set_nested_field(original_pd1, new_message.pd1, "pd1_3", "xon_5")
    set_nested_field(original_pd1, new_message.pd1, "pd1_3", "xon_7")
    set_nested_field(original_pd1, new_message.pd1, "pd1_3", "xon_9")

    set_nested_field(original_pd1, new_message.pd1, "pd1_4", "xcn_1")
    set_nested_field(original_pd1, new_message.pd1, "pd1_4", "xcn_3")
    set_nested_field(original_pd1, new_message.pd1, "pd1_4", "xcn_4")
    set_nested_field(original_pd1, new_message.pd1, "pd1_4", "xcn_6")

    if (
        hasattr(original_pd1, "pd1_3")
        and hasattr(original_pd1.pd1_3, "xon_6")
        and hasattr(original_pd1.pd1_3.xon_6, "hd_1")
        and original_pd1.pd1_3.xon_6.hd_1
    ):
        new_message.pd1.pd1_3.xon_6.hd_1 = original_pd1.pd1_3.xon_6.hd_1

    if (
        hasattr(original_pd1, "pd1_3")
        and hasattr(original_pd1.pd1_3, "xon_8")
        and hasattr(original_pd1.pd1_3.xon_8, "hd_1")
        and original_pd1.pd1_3.xon_8.hd_1
    ):
        new_message.pd1.pd1_3.xon_8.hd_1 = original_pd1.pd1_3.xon_8.hd_1

    if (
        hasattr(original_pd1, "pd1_4")
        and hasattr(original_pd1.pd1_4, "xcn_2")
        and hasattr(original_pd1.pd1_4.xcn_2, "fn_1")
        and original_pd1.pd1_4.xcn_2.fn_1
    ):
        new_message.pd1.pd1_4.xcn_2.fn_1 = original_pd1.pd1_4.xcn_2.fn_1

    # for i in range(1, 15):
    #     field_name = f"pd1_{i}"
    #     if hasattr(original_pd1, field_name) and field_name not in ["pd1_3", "pd1_4"]:
    #         field_value = getattr(original_pd1, field_name)
    #         if field_value:
    #             setattr(new_message.pd1, field_name, field_value)
