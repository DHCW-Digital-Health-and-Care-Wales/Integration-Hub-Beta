from field_utils_lib import copy_segment_fields_in_range, set_nested_field
from hl7apy.core import Message


def map_msh(original_hl7_message: Message, new_message: Message) -> None:
    original_msh = original_hl7_message.msh

    # MSH
    # MSH.1 and MSH.2 are mandatory fields in HL7 messages, so we set them directly.
    new_message.msh.msh_1 = original_msh.msh_1
    new_message.msh.msh_2 = original_msh.msh_2

    set_nested_field(original_msh, new_message.msh, "msh_3.hd_1")
    set_nested_field(original_msh, new_message.msh, "msh_4.hd_1")
    set_nested_field(original_msh, new_message.msh, "msh_5.hd_1")
    set_nested_field(original_msh, new_message.msh, "msh_6.hd_1")
    set_nested_field(original_msh, new_message.msh, "msh_7.ts_1")
    set_nested_field(original_msh, new_message.msh, "msh_8")
    set_nested_field(original_msh, new_message.msh, "msh_9.msg_1")
    set_nested_field(original_msh, new_message.msh, "msh_9.msg_2")

    # Always ensure MSH.9 exists before setting msg_3
    if not getattr(new_message.msh, "msh_9", None):
        new_message.msh.msh_9 = new_message.msh.add_field("msh_9")
    new_message.msh.msh_9.msg_3 = "ADT_A05"

    # MSH.10-12 are mandatory fields in HL7 messages, so we set them directly.
    new_message.msh.msh_10 = original_msh.msh_10
    new_message.msh.msh_11 = original_msh.msh_11

    # Always ensure MSH.12 exists before setting the version ID
    if not getattr(new_message.msh, "msh_12", None):
        new_message.msh.msh_12 = new_message.msh.add_field("msh_12")
    new_message.msh.msh_12.vid_1 = "2.5"

    copy_segment_fields_in_range(original_msh, new_message.msh, "msh", start=13, end=21)
