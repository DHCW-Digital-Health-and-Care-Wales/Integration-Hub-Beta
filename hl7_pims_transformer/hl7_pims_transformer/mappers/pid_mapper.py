from hl7apy.core import Message

from ..utils.field_utils import get_hl7_field_value, set_nested_field


def map_pid(original_hl7_message: Message, new_message: Message) -> None:
    original_pid = getattr(original_hl7_message, "pid", None)
    if not original_pid:
        return  # No PID segment

    # trigger event for A28 specific logic
    trigger_event = get_hl7_field_value(original_hl7_message, "msh.msh_9.msg_2")
    is_a28_message = trigger_event == "A28"

    original_pid_3_rep1_cx_1 = get_hl7_field_value(original_pid, "pid_3[0].cx_1")
    pid3_rep1 = new_message.pid.add_field("pid_3")

    # if the cx_1 subfield on pid_3[0] exists and is not empty, and cx_5 is "NI"
    if original_pid_3_rep1_cx_1 and get_hl7_field_value(original_pid, "pid_3[0].cx_5") == "NI":

        # check if NHS number starts with N3 or N4
        nhs_number_prefix = original_pid_3_rep1_cx_1[:2].upper() if len(original_pid_3_rep1_cx_1) >= 2 else ""
        is_n3_or_n4_prefix = nhs_number_prefix in ["N3", "N4"]

        if is_a28_message:
            if is_n3_or_n4_prefix:
                # for N3 or N4 prefix set values
                pid3_rep1.cx_1 = original_pid_3_rep1_cx_1
                pid3_rep1.cx_4.hd_1 = "108"
                pid3_rep1.cx_5 = "LI"
            else:
                # for not N3 or N4 prefix set fields to blank
                pid3_rep1.cx_1 = ""
                pid3_rep1.cx_4.hd_1 = ""
                pid3_rep1.cx_5 = ""
        else:
            # for non-A28 messages use original logic
            pid3_rep1.cx_1 = original_pid_3_rep1_cx_1
            pid3_rep1.cx_4.hd_1 = "NHS"
            pid3_rep1.cx_5 = "NH"

    original_pid_3_rep2_cx_1 = get_hl7_field_value(original_pid, "pid_3[1].cx_1")
    # if the cx_1 subfield on pid_3[1] exists and is not empty, and cx_5 is "PI"
    if original_pid_3_rep2_cx_1 and get_hl7_field_value(original_pid, "pid_3[1].cx_5") == "PI":
        pid3_rep2 = new_message.pid.add_field("pid_3")
        pid3_rep2.cx_1 = original_pid_3_rep2_cx_1
        pid3_rep2.cx_4.hd_1 = "103"
        pid3_rep2.cx_5 = "PI"

    set_nested_field(original_pid, new_message.pid, "pid_5.xpn_1.fn_1")

    pid_5_fields = ["xpn_2", "xpn_3", "xpn_4", "xpn_5"]
    for field in pid_5_fields:
        set_nested_field(original_pid, new_message.pid, f"pid_5.{field}")

    set_nested_field(original_pid, new_message.pid, "pid_8")

    # SAD does not exist in HL7 v2.3.1 so it's mapped manually
    new_message.pid.pid_11.xad_1.sad_1 = original_pid.pid_11.xad_1

    pid_11_fields = ["xad_2", "xad_3", "xad_4", "xad_5"]
    for field in pid_11_fields:
        set_nested_field(original_pid, new_message.pid, f"pid_11.{field}")

    # Map all repetitions of pid_13
    if hasattr(original_pid, "pid_13"):
        for rep_count, original_pid_13 in enumerate(original_pid.pid_13):
            new_pid_13_repetition = new_message.pid.add_field("pid_13")
            set_nested_field(original_pid_13, new_pid_13_repetition, "xtn_1")

    set_nested_field(original_pid, new_message.pid, "pid_14.xtn_1")

    # death date and time: trim at first "+" if length > 6, otherwise set to '""'
    original_pid29_ts1 = get_hl7_field_value(original_pid, "pid_29.ts_1")
    new_message.pid.pid_29.ts_1 = original_pid29_ts1.split("+")[0] if len(original_pid29_ts1) > 6 else '""'
