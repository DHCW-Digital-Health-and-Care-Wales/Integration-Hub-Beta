from hl7apy.core import Message

from ..utils.field_utils import set_nested_field


def map_nk1(original_hl7_message: Message, new_message: Message) -> None:
    original_nk1 = getattr(original_hl7_message, "nk1", None)
    if original_nk1 is None:
        return  # No NK1 segment

    set_nested_field(original_nk1, new_message.nk1, "nk1_2", "xpn_2")
    set_nested_field(original_nk1, new_message.nk1, "nk1_2", "xpn_7")
    set_nested_field(original_nk1, new_message.nk1, "nk1_3", "ce_1")
    set_nested_field(original_nk1, new_message.nk1, "nk1_4", "xad_2")
    set_nested_field(original_nk1, new_message.nk1, "nk1_4", "xad_7")
    set_nested_field(original_nk1, new_message.nk1, "nk1_5", "xtn_1")

    if (
        hasattr(original_nk1, "nk1_2")
        and hasattr(original_nk1.nk1_2, "xpn_1")
        and hasattr(original_nk1.nk1_2.xpn_1, "fn_1")
        and original_nk1.nk1_2.xpn_1.fn_1
    ):
        new_message.nk1.nk1_2.xpn_1.fn_1 = original_nk1.nk1_2.xpn_1.fn_1

    if (
        hasattr(original_nk1, "nk1_4")
        and hasattr(original_nk1.nk1_4, "xad_1")
        and hasattr(original_nk1.nk1_4.xad_1, "sad_1")
        and original_nk1.nk1_4.xad_1.sad_1
    ):
        new_message.nk1.nk1_4.xad_1.sad_1 = original_nk1.nk1_4.xad_1.sad_1

        # for i in range(1, 40):
    #     field_name = f"nk1_{i}"
    #     if hasattr(original_nk1, field_name) and field_name not in ["nk1_2", "nk1_3", "nk1_4", "nk1_5"]:
    #         field_value = getattr(original_nk1, field_name)
    #         if field_value:
    #             setattr(new_message.nk1, field_name, field_value)
