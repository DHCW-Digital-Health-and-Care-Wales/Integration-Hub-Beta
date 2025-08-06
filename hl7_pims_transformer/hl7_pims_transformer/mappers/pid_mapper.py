from hl7apy.core import Message

from ..utils.field_utils import set_nested_field


def map_pid(original_hl7_message: Message, new_message: Message) -> None:
    original_pid = getattr(original_hl7_message, "pid", None)
    if original_pid is None:
        return  # No PID segment

    set_nested_field(original_pid, new_message.pid, "pid_5.xpn_1.fn_1")

    pid_5_fields = ["xpn_2", "xpn_3", "xpn_4", "xpn_5"]
    for field in pid_5_fields:
        set_nested_field(original_pid, new_message.pid, f"pid_5.{field}")

    set_nested_field(original_pid, new_message.pid, "pid_8")

    # SAD does not exist on HL7 v2.3.1 so it's mapped manually
    new_message.pid.pid_11.xad_1.sad_1 = original_pid.pid_11.xad_1

    pid_11_fields = ["xad_2", "xad_3", "xad_4", "xad_5"]
    for field in pid_11_fields:
        set_nested_field(original_pid, new_message.pid, f"pid_11.{field}")

    # Map all repetitions of pid_13
    # TODO check if mapping rules for pid_13 specify all repetitions
    if hasattr(original_pid, "pid_13"):
        for rep_count, original_pid_13 in enumerate(original_pid.pid_13):
            new_pid_13_repetition = new_message.pid.add_field("pid_13")
            set_nested_field(original_pid_13, new_pid_13_repetition, "xtn_1")

    set_nested_field(original_pid, new_message.pid, "pid_14.xtn_1")
