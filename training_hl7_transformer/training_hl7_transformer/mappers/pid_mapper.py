from hl7apy.core import Message
from field_utils_lib import copy_segment_fields_in_range, get_hl7_field_value, set_nested_field



def map_pid(original_message: Message, new_message: Message) -> None:
    pid_segment = original_message.pid
    new_pid = new_message.pid
    copy_segment_fields_in_range(pid_segment, new_pid, "pid", start=1, end=39)
    original_patient_name = get_hl7_field_value(pid_segment, "pid_5.xpn_1.fn_1")
    if not original_patient_name:
        original_patient_name = get_hl7_field_value(pid_segment, "pid_5.xpn_1.fn_1")

    original_given = get_hl7_field_value(pid_segment, "pid_5.xpn_2")
    original_middle = get_hl7_field_value(pid_segment, "pid_5.xpn_3")


    original_name_bits = [p for p in [original_patient_name, original_given, original_middle] if p]
    original_name = "^".join(original_name_bits)

    if original_patient_name:
        try:
            new_pid.pid_5.xpn_1.fn_1.value = original_patient_name.upper()
        except AttributeError:
            new_pid.pid_5.xpn_1.value = original_patient_name.upper()
    if original_given:
        new_pid.pid_5.xpn_2.value = original_given.upper()
    if original_middle:
        new_pid.pid_5.xpn_3.value = original_middle.upper()

    transformed_name_parts = [p.upper() for p in original_name_bits]
    transformed_name = "^".join(transformed_name_parts)

    if original_patient_name:
        print(
            f"  PID-5 transformed: '{original_name}' -> '{transformed_name}'"
        )
    else:
        print("  PID-5 not present")
    print()
    return {
        "original_patient_name": original_name or "",
        "transformed_patient_name": transformed_name,
    }
