from hl7apy.core import Message

from ..utils.field_utils import get_hl7_field_value, set_nested_field


def map_pid(original_hl7_message: Message, new_message: Message) -> None:
    original_pid = getattr(original_hl7_message, "pid", None)
    if original_pid is None:
        return  # No PD1 segment

    # PID
    set_nested_field(original_pid, new_message.pid, "pid_1")

    # if the cx_1 subfield on pid_2 is empty we default to the entire pid_2 field
    pid2_value = get_hl7_field_value(original_pid, "pid_2.cx_1") or get_hl7_field_value(original_pid, "pid_2")

    original_msh = original_hl7_message.msh
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
            if msh3_value == "224":
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
