from typing import Any, Optional

from chemo_messages import chemo_messages
from hl7apy.core import Message
from hl7apy.parser import parse_message

# from .chemocare_transformer import transform_chemocare


def transform_chemocare(hl7_msg: Message) -> Message:
    return create_new_message(hl7_msg)


def create_new_message(original_message: Message) -> Message:
    original_msh = original_message.msh
    original_pid = original_message.pid
    original_pd1 = original_message.pd1
    original_nk1 = original_message.nk1

    new_message = Message(version="2.5")

    # MSH
    # MSH.1 and MSH.2 are mandatory fields in HL7 messages, so we set them directly.
    new_message.msh.msh_1 = original_msh.msh_1
    new_message.msh.msh_2 = original_msh.msh_2

    set_nested_field(original_msh, new_message.msh, "msh_3", "hd_1")
    set_nested_field(original_msh, new_message.msh, "msh_4", "hd_1")
    set_nested_field(original_msh, new_message.msh, "msh_5", "hd_1")
    set_nested_field(original_msh, new_message.msh, "msh_6", "hd_1")
    set_nested_field(original_msh, new_message.msh, "msh_7", "ts_1")
    set_nested_field(original_msh, new_message.msh, "msh_8")
    set_nested_field(original_msh, new_message.msh, "msh_9", "msg_1")
    set_nested_field(original_msh, new_message.msh, "msh_9", "msg_2")

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

    for i in range(13, 22):
        field_name = f"msh_{i}"
        set_nested_field(original_msh, new_message.msh, field_name)

    # EVN
    set_nested_field(original_message, new_message, "evn")

    # PID
    set_nested_field(original_pid, new_message.pid, "pid_1")

    # if the cx_1 subfield on pid_2 is empty we default to the entire pid_2 field
    pid2_value = get_hl7_field_value(original_pid, "pid_2.cx_1") or get_hl7_field_value(original_pid, "pid_2")
    # if the hd_1 subfield on msh_3 is empty we default to the entire msh_3 field
    msh3_value = get_hl7_field_value(original_msh, "msh_3.hd_1") or get_hl7_field_value(original_msh, "msh_3")

    pid3_rep1 = new_message.pid.add_field("pid_3")
    pid3_rep1.cx_4.hd_1 = "NHS"
    pid3_rep1.cx_5 = "NH"

    pid3_rep2 = new_message.pid.add_field("pid_3")
    pid3_rep2.cx_4.hd_1 = "NHS"
    pid3_rep2.cx_5 = "PI"

    if pid2_value:
        pid3_rep1.cx_1 = pid2_value

        if msh3_value:
            # Mapping rules based on msh.3.hd_1
            health_board = ""
            if msh3_value == "244":
                health_board = "VCC"
            elif msh3_value == "212":
                health_board = "BCUCCC"
            elif msh3_value == "192":
                health_board = "SWW"
            elif msh3_value == "245":
                health_board = "SEW"

            # If MSH.3.HD_1 has a different value to one of the 4 expected health boards - it will NOT be mapped
            if health_board:
                pid3_rep2.cx_1 = f"{health_board}{pid2_value}"

    if (
        hasattr(original_pid, "pid_5")
        and hasattr(original_pid.pid_5, "xpn_1")
        and hasattr(original_pid.pid_5.xpn_1, "fn_1")
        and original_pid.pid_5.xpn_1.fn_1
    ):
        new_message.pid.pid_5.xpn_1.fn_1 = original_pid.pid_5.xpn_1.fn_1

    set_nested_field(original_pid, new_message.pid, "pid_5", "xpn_2")
    set_nested_field(original_pid, new_message.pid, "pid_5", "xpn_3")
    set_nested_field(original_pid, new_message.pid, "pid_5", "xpn_4")
    set_nested_field(original_pid, new_message.pid, "pid_5", "xpn_5")
    set_nested_field(original_pid, new_message.pid, "pid_5", "xpn_6")
    set_nested_field(original_pid, new_message.pid, "pid_5", "xpn_7")
    set_nested_field(original_pid, new_message.pid, "pid_5", "xpn_8")

    if (
        hasattr(original_pid, "pid_5")
        and hasattr(original_pid.pid_5, "xpn_9")
        and hasattr(original_pid.pid_5.xpn_9, "ce_1")
        and original_pid.pid_5.xpn_9.ce_1
    ):
        new_message.pid.pid_5.xpn_9.ce_1 = original_pid.pid_5.xpn_9.ce_1

    set_nested_field(original_pid, new_message.pid, "pid_5", "xpn_10")
    set_nested_field(original_pid, new_message.pid, "pid_5", "xpn_11")

    if (
        hasattr(original_pid, "pid_6")
        and hasattr(original_pid.pid_6, "xpn_1")
        and hasattr(original_pid.pid_6.xpn_1, "fn_1")
        and original_pid.pid_6.xpn_1.fn_1
    ):
        new_message.pid.pid_6.xpn_1.fn_1 = original_pid.pid_6.xpn_1.fn_1

    set_nested_field(original_pid, new_message.pid, "pid_7")
    set_nested_field(original_pid, new_message.pid, "pid_8")

    if (
        hasattr(original_pid, "pid_9")
        and hasattr(original_pid.pid_9, "xpn_1")
        and hasattr(original_pid.pid_9.xpn_1, "fn_1")
        and original_pid.pid_9.xpn_1.fn_1
    ):
        new_message.pid.pid_9.xpn_1.fn_1 = original_pid.pid_9.xpn_1.fn_1

    set_nested_field(original_pid, new_message.pid, "pid_10", "ce_1")

    if (
        hasattr(original_pid, "pid_11")
        and hasattr(original_pid.pid_11, "xad_1")
        and hasattr(original_pid.pid_11.xad_1, "sad_1")
        and original_pid.pid_11.xad_1.sad_1
    ):
        new_message.pid.pid_11.xad_1.sad_1 = original_pid.pid_11.xad_1.sad_1

    set_nested_field(original_pid, new_message.pid, "pid_11", "xad_2")
    set_nested_field(original_pid, new_message.pid, "pid_11", "xad_3")
    set_nested_field(original_pid, new_message.pid, "pid_11", "xad_4")
    set_nested_field(original_pid, new_message.pid, "pid_11", "xad_5")
    set_nested_field(original_pid, new_message.pid, "pid_11", "xad_7")
    set_nested_field(original_pid, new_message.pid, "pid_11", "xad_8")

    set_nested_field(original_pid, new_message.pid, "pid_13", "xtn_1")
    set_nested_field(original_pid, new_message.pid, "pid_13", "xtn_2")

    set_nested_field(original_pid, new_message.pid, "pid_14", "xtn_1")
    set_nested_field(original_pid, new_message.pid, "pid_14", "xtn_2")

    set_nested_field(original_pid, new_message.pid, "pid_17", "ce_1")
    set_nested_field(original_pid, new_message.pid, "pid_22", "ce_1")
    set_nested_field(original_pid, new_message.pid, "pid_29", "ts_1")

    pid32_value = get_hl7_field_value(original_pid, "pid_32")
    if pid32_value:
        new_message.pid.pid_31 = pid32_value

    # PV1
    set_nested_field(original_message, new_message, "pv1")

    # PD1 specific mappings
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

    # NK1 specific mappings
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

    segment_names = ["pv2", "obx", "al1", "dg1", "pr1", "gt1", "in1", "in2", "in3"]

    for segment_name in segment_names:
        if hasattr(original_message, segment_name):
            segment = getattr(original_message, segment_name)
            if segment:
                setattr(new_message, segment_name, segment)

    return new_message


def get_hl7_field_value(hl7_segment: Any, field_path: str) -> str:
    """
    Safely retrieves the string value of a nested HL7 field using a dot-separated path.

    Traverses the HL7 segment hierarchy following the provided path,
    handling missing attributes and empty values gracefully (returns empty string to maintain compatibility with hl7apy)
    Works with hl7apy objects which may have .value attributes or can be converted to strings.
    Example usage:
    - get_hl7_field_value(original_msh, "msh_4.hd_1") = "HOSPITAL NAME"
    - get_hl7_field_value(original_pid, "pid_5.xpn_1.fn_1") = "TEST"
    - get_hl7_field_value(original_msh, "nonexistent.field") = ""
    """
    current_element = hl7_segment
    # Loop through each attribute in the field path in order
    for field_name in field_path.split("."):
        try:
            current_element = getattr(current_element, field_name)
            if not current_element:
                return ""  # Empty field
        except (AttributeError, IndexError):
            return ""  # Non-existent field

    # Assuming all hl7apy fields have a .value - see docs https://crs4.github.io/hl7apy/api_docs/core.html
    if current_element is not None:
        field_value = current_element.value
        return str(field_value) if field_value is not None else ""
    return ""


def set_nested_field(source_msg: Any, target_msg: Any, field: str, subfield: Optional[str] = None) -> None:
    """
    Safely copy a field or nested field (e.g., msh_7.ts_1) from source to target message.
    Only copies if the source field (and subfield, if provided) exist and are populated.
    Example usage:
    - set_nested_field(original_msh, new_message.msh, "msh_7", "ts_1") - nested field
    - set_nested_field(original_msh, new_message.msh, "msh_8")         - top-level field
    """
    if hasattr(source_msg, field):
        src_field = getattr(source_msg, field)
        if src_field:
            if subfield:
                if hasattr(src_field, subfield):
                    value = getattr(src_field, subfield)
                    if value:
                        setattr(getattr(target_msg, field), subfield, value)
            else:
                setattr(target_msg, field, src_field)


def print_original_msg(msg: Message, key: Optional[str] = None) -> None:
    print("\nORIGINAL {} Message:".format(key if key else ""))
    print("=" * 50)
    original_message = msg.to_er7()
    print(original_message.replace("\r", "\n"))
    print("=" * 50)


for key, message in chemo_messages.items():
    hl7_msg = parse_message(message)
    print_original_msg(hl7_msg, key)
    transformed_msg = transform_chemocare(hl7_msg)
    updated_transformed_msg = transformed_msg.to_er7().replace("\r", "\n")
    print("\nTRANSFORMED {} message:".format(key))
    print("=" * 50)
    print(updated_transformed_msg)
