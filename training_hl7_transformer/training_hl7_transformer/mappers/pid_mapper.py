from hl7apy.core import Message
from field_utils_lib import copy_segment_fields_in_range, get_hl7_field_value, set_nested_field



def map_pid(original_message: Message, new_message: Message) -> None:
    pid_segment = original_message.pid
    new_pid = new_message.pid
    copy_segment_fields_in_range(pid_segment, new_pid, "pid", start=1, end=30)
    original_patient_name = get_hl7_field_value(pid_segment, "pid_5")

    new_patient_name = ""

    if original_patient_name:
        new_patient_name = original_patient_name.upper()
        set_nested_field(new_pid, "pid_5", new_patient_name)

    if original_patient_name:
        print(
            f"  PID-5 transformed: '{original_patient_name}' -> '{new_patient_name}'"
        )
    else:
        print("  PID-5 not present")

    return {
        "original_patient_name": original_patient_name or "",
        "transformed_patient_name": new_patient_name,
    }
