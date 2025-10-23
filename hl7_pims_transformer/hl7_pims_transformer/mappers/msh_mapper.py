from field_utils_lib import get_hl7_field_value, set_nested_field
from hl7apy.core import Message

from ..utils.remove_timezone_from_datetime import remove_timezone_from_datetime


def map_msh(original_hl7_message: Message, new_message: Message) -> None:
    original_msh = original_hl7_message.msh

    # MSH.1 and MSH.2 are mandatory fields in HL7 messages, so we set them directly.
    new_message.msh.msh_1 = original_msh.msh_1
    new_message.msh.msh_2 = original_msh.msh_2

    new_message.msh.msh_3.hd_1 = "103"
    new_message.msh.msh_4.hd_1 = "103"
    new_message.msh.msh_5.hd_1 = "200"
    new_message.msh.msh_6.hd_1 = "200"

    # MSH.7 - remove timezone from timestamp for MPI compatibility
    original_msh7_ts1 = get_hl7_field_value(original_msh, "msh_7.ts_1")
    if original_msh7_ts1:
        new_message.msh.msh_7.ts_1 = remove_timezone_from_datetime(original_msh7_ts1)

    set_nested_field(original_msh, new_message.msh, "msh_8")

    # Always ensure MSH.9 exists
    if not getattr(new_message.msh, "msh_9", None):
        new_message.msh.msh_9 = new_message.msh.add_field("msh_9")

    new_message.msh.msh_9.msg_1 = "ADT"
    # possible values are A04, A08 and A40
    original_message_type_trigger_event = original_msh.msh_9.msg_2

    # Set msg_2 and msg_3 based on original trigger event (msg_2)
    if original_message_type_trigger_event.value == "A04":
        new_message.msh.msh_9.msg_2 = "A28"
        new_message.msh.msh_9.msg_3 = "ADT_A05"

    elif original_message_type_trigger_event.value == "A08":
        new_message.msh.msh_9.msg_2 = "A31"
        new_message.msh.msh_9.msg_3 = "ADT_A05"

    else:
        new_message.msh.msh_9.msg_2 = "A40"
        new_message.msh.msh_9.msg_3 = "ADT_A39"

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
