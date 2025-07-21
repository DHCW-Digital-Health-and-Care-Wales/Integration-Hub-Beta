from hl7apy.core import Message
from hl7apy.parser import parse_message

# from .chemocare_transformer import transform_chemocare


def transform_chemocare(hl7_msg: Message) -> Message:
    return create_new_message(hl7_msg)


def create_new_message(original_message: Message) -> Message:
    original_msh = original_message.msh
    original_pid = original_message.pid

    new_message = Message(version="2.5")

    new_message.msh.msh_1 = original_msh.msh_1
    new_message.msh.msh_2 = original_msh.msh_2

    if hasattr(original_msh, "msh_3") and original_msh.msh_3.hd_1:
        new_message.msh.msh_3.hd_1 = original_msh.msh_3.hd_1

    if hasattr(original_msh, "msh_4") and original_msh.msh_4.hd_1:
        new_message.msh.msh_4.hd_1 = original_msh.msh_4.hd_1

    if hasattr(original_msh, "msh_5") and original_msh.msh_5.hd_1:
        new_message.msh.msh_5.hd_1 = original_msh.msh_5.hd_1

    if hasattr(original_msh, "msh_6") and original_msh.msh_6.hd_1:
        new_message.msh.msh_6.hd_1 = original_msh.msh_6.hd_1

    if hasattr(original_msh, "msh_7") and original_msh.msh_7.ts_1:
        new_message.msh.msh_7.ts_1 = original_msh.msh_7.ts_1

    if hasattr(original_msh, "msh_9") and original_msh.msh_9:
        new_message.msh.msh_9.msg_1 = _safe_get_value(original_msh.msh_9, "msg_1") or _safe_get_value(
            original_msh.msh_9, "msh_9_1"
        )
        new_message.msh.msh_9.msg_2 = _safe_get_value(original_msh.msh_9, "msg_2") or _safe_get_value(
            original_msh.msh_9, "msh_9_2"
        )
        new_message.msh.msh_9.msg_3 = "ADT_A05"

    if hasattr(original_msh, "msh_10") and original_msh.msh_10:
        new_message.msh.msh_10 = original_msh.msh_10

    if hasattr(original_msh, "msh_11") and original_msh.msh_11.pt_1:
        new_message.msh.msh_11.pt_1 = original_msh.msh_11.pt_1

    new_message.msh.msh_12.vid_1 = "2.5"

    # Copy other MSH fields that might exist
    for i in range(13, 20):
        field_name = f"msh_{i}"
        if hasattr(original_msh, field_name):
            field_value = getattr(original_msh, field_name)
            if field_value:
                setattr(new_message.msh, field_name, field_value)

    msh20_value = _safe_get_value(original_msh, "msh_20")
    msh21_value = _safe_get_value(original_msh, "msh_21")
    if msh20_value:
        new_message.msh.msh_21.ei_1 = msh20_value
    elif msh21_value:
        new_message.msh.msh_21.ei_1 = msh21_value

    if hasattr(original_pid, "pid_1") and original_pid.pid_1:
        new_message.pid.pid_1 = original_pid.pid_1

    pid2_value = _safe_get_value(original_pid, "pid_2.pid_2_1") or _safe_get_value(original_pid, "pid_2")
    msh3_value = _safe_get_value(original_msh, "msh_3.msh_3_1") or _safe_get_value(original_msh, "msh_3")

    if pid2_value:
        pid3_rep1 = new_message.pid.add_field("pid_3")
        pid3_rep1.cx_1 = pid2_value
        pid3_rep1.cx_2 = f"{pid2_value}{msh3_value}" if msh3_value else pid2_value
        pid3_rep1.cx_4.hd_1 = "NHS"
        pid3_rep1.cx_5 = "NH"

    if msh3_value:
        pid3_rep2 = new_message.pid.add_field("pid_3")
        pid3_rep2.cx_1 = msh3_value
        pid3_rep2.cx_4.hd_1 = "NHS"
        pid3_rep2.cx_5 = "PI"

    if hasattr(original_pid, "pid_5") and original_pid.pid_5:
        new_message.pid.pid_5 = original_pid.pid_5

    if hasattr(original_pid, "pid_7") and original_pid.pid_7:
        new_message.pid.pid_7 = original_pid.pid_7

    if hasattr(original_pid, "pid_8") and original_pid.pid_8:
        new_message.pid.pid_8 = original_pid.pid_8

    if hasattr(original_pid, "pid_11") and original_pid.pid_11:
        new_message.pid.pid_11 = original_pid.pid_11

    if hasattr(original_pid, "pid_13") and original_pid.pid_13:
        new_message.pid.pid_13 = original_pid.pid_13

    pid32_value = _safe_get_value(original_pid, "pid_32")
    if pid32_value:
        new_message.pid.pid_31 = pid32_value

    if hasattr(original_message, "evn") and original_message.evn:
        new_message.evn = original_message.evn

    if hasattr(original_message, "pv1") and original_message.pv1:
        new_message.pv1 = original_message.pv1

    segment_names = ["pd1", "nk1", "pv2", "obx", "al1", "dg1", "pr1", "gt1", "in1", "in2", "in3"]

    for segment_name in segment_names:
        if hasattr(original_message, segment_name):
            segment = getattr(original_message, segment_name)
            if segment:
                setattr(new_message, segment_name, segment)

    return new_message


# Used to access HL7 nested fields directly (without crashing)
def _safe_get_value(segment, field_path: str) -> str:
    try:
        current = segment
        for part in field_path.split("."):
            current = getattr(current, part)
        return current.value if hasattr(current, "value") else str(current)
    except (AttributeError, IndexError):
        return ""


message_body = (
    "MSH|^~\\&|245|245|100|100|20250701141950||ADT^A31|596887414401487|P|2.4|||NE|NE EVN||20250701141950\r"
    "PID|1|1000000001^^^^NH|1000000001^^^^NH~00rb00^^^^PI||TEST^TEST||20000101000000|M|||1 Street^Town^Rhondda, cynon, taff^^CF11 9AD||07000000001\r"
    "PV1||U\r"
)


original_hl7_msg = parse_message(message_body)

print("\nORIGINAL HL7 Message:")
print("=" * 50)
original_message = original_hl7_msg.to_er7()
formatted_original = original_message.replace("\r", "\n")
print(formatted_original)
print("=" * 50)

transformed_hl7_msg = transform_chemocare(original_hl7_msg)
updated_message = transformed_hl7_msg.to_er7()
print("\nTRANSFORMED HL7 Message:")
print("=" * 50)
formatted_message = updated_message.replace("\r", "\n")
print(formatted_message)
print("=" * 50)
