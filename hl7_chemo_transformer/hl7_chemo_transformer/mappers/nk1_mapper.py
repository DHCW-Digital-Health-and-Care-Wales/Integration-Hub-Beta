from field_utils_lib import set_nested_field
from hl7apy.core import Message


def map_nk1(original_hl7_message: Message, new_message: Message) -> None:
    original_nk1 = getattr(original_hl7_message, "nk1", None)
    if original_nk1 is None:
        return  # No NK1 segment

    set_nested_field(original_nk1, new_message.nk1, "nk1_2.xpn_2")
    set_nested_field(original_nk1, new_message.nk1, "nk1_2.xpn_7")
    set_nested_field(original_nk1, new_message.nk1, "nk1_3.ce_1")
    set_nested_field(original_nk1, new_message.nk1, "nk1_4.xad_2")
    set_nested_field(original_nk1, new_message.nk1, "nk1_4.xad_7")
    set_nested_field(original_nk1, new_message.nk1, "nk1_5.xtn_1")

    set_nested_field(original_nk1, new_message.nk1, "nk1_2.xpn_1.fn_1")
    set_nested_field(original_nk1, new_message.nk1, "nk1_4.xad_1.sad_1")
