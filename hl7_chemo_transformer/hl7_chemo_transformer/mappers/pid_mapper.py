from hl7apy.core import Message

from ..utils.field_utils import get_hl7_field_value, set_nested_field

HEALTH_BOARD_MAPPING = {
    "224": "VCC",
    "212": "BCUCC",
    "192": "SWWCC",
    "245": "SEWCC"
}


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
    pid3_rep2.cx_4.hd_1 = msh3_value
    pid3_rep2.cx_5 = "PI"

    if pid2_value:
        pid3_rep1.cx_1 = pid2_value

        if msh3_value:
            # Mapping rules based on msh.3.hd_1
            health_board = HEALTH_BOARD_MAPPING.get(msh3_value, "")

            # If MSH.3.HD_1 has a different value to one of the 4 expected health boards - it will NOT be mapped
            if health_board:
                pid3_rep2.cx_1 = f"{health_board}{pid2_value}"

    set_nested_field(original_pid, new_message.pid, "pid_5.xpn_1.fn_1")

    pid_5_fields = ["xpn_2", "xpn_3", "xpn_4", "xpn_5", "xpn_6", "xpn_7", "xpn_8"]
    for field in pid_5_fields:
        set_nested_field(original_pid, new_message.pid, f"pid_5.{field}")

    set_nested_field(original_pid, new_message.pid, "pid_5.xpn_9.ce_1")

    set_nested_field(original_pid, new_message.pid, "pid_5.xpn_10")
    set_nested_field(original_pid, new_message.pid, "pid_5.xpn_11")

    set_nested_field(original_pid, new_message.pid, "pid_6.xpn_1.fn_1")

    set_nested_field(original_pid, new_message.pid, "pid_7")
    set_nested_field(original_pid, new_message.pid, "pid_8")

    set_nested_field(original_pid, new_message.pid, "pid_9.xpn_1.fn_1")

    set_nested_field(original_pid, new_message.pid, "pid_10.ce_1")

    set_nested_field(original_pid, new_message.pid, "pid_11.xad_1.sad_1")

    pid_11_fields = ["xad_2", "xad_3", "xad_4", "xad_5", "xad_7", "xad_8"]
    for field in pid_11_fields:
        set_nested_field(original_pid, new_message.pid, f"pid_11.{field}")

    # All repetitions of pid_13 should be mapped as per the mapping rules
    if hasattr(original_pid, "pid_13"):
        for rep_count, original_pid_13 in enumerate(original_pid.pid_13):
            new_pid_13_repetition = new_message.pid.add_field("pid_13")
            for subfield in ["xtn_1", "xtn_2", "xtn_4"]:
                set_nested_field(original_pid_13, new_pid_13_repetition, subfield)

    set_nested_field(original_pid, new_message.pid, "pid_14.xtn_1")
    set_nested_field(original_pid, new_message.pid, "pid_14.xtn_2")
    set_nested_field(original_pid, new_message.pid, "pid_17.ce_1")
    set_nested_field(original_pid, new_message.pid, "pid_22.ce_1")
    set_nested_field(original_pid, new_message.pid, "pid_29.ts_1")
    set_nested_field(original_pid, new_message.pid, "pid_32")
