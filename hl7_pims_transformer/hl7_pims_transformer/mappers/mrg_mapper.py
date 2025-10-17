from field_utils_lib import set_nested_field
from hl7apy.core import Message


def map_mrg(original_hl7_message: Message, new_message: Message) -> None:
    original_mrg = getattr(original_hl7_message, "mrg", None)
    if not original_mrg:
        return  # No MRG segment

    original_message_type_trigger_event = original_hl7_message.msh.msh_9.msg_2.value
    if original_message_type_trigger_event == "A40":
        set_nested_field(original_mrg, new_message.mrg, "mrg_1.cx_1")
        new_message.mrg.mrg_1.cx_4.hd_1 = "103"
        new_message.mrg.mrg_1.cx_5 = "PI"
