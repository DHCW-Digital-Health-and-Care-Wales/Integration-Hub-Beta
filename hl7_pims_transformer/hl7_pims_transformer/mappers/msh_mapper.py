from hl7apy.core import Message

from ..utils.field_utils import set_nested_field


def map_msh(original_hl7_message: Message, new_message: Message) -> None:
    original_msh = original_hl7_message.msh

    # MSH
    # MSH.1 and MSH.2 are mandatory fields in HL7 messages, so we set them directly.
    new_message.msh.msh_1 = original_msh.msh_1
    new_message.msh.msh_2 = original_msh.msh_2

    new_message.msh.msh_3.hd_1 = "103"
    new_message.msh.msh_4.hd_1 = "103"
    new_message.msh.msh_5.hd_1 = "200"
    new_message.msh.msh_6.hd_1 = "200"

    set_nested_field(original_msh, new_message.msh, "msh_8")

    # Always ensure MSH.9 exists before setting msg_1
    if not getattr(new_message.msh, "msh_9", None):
        new_message.msh.msh_9 = new_message.msh.add_field("msh_9")
    new_message.msh.msh_9.msg_1 = "ADT"

    # MSH.10-12 are mandatory fields in HL7 messages
    new_message.msh.msh_10 = original_msh.msh_10
    new_message.msh.msh_11 = original_msh.msh_11
    # Always ensure MSH.12 exists before setting the version ID
    if not getattr(new_message.msh, "msh_12", None):
        new_message.msh.msh_12 = new_message.msh.add_field("msh_12")
    new_message.msh.msh_12.vid_1 = "2.5"

    set_nested_field(original_msh, new_message.msh, "msh_13")

    new_message.msh.msh_17 = "GBR"
    new_message.msh.msh_19.ce_1 = "EN"
