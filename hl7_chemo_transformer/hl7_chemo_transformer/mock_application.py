from hl7apy.core import Message
from hl7apy.parser import parse_message

# from .chemocare_transformer import transform_chemocare


def transform_chemocare(hl7_msg: Message) -> Message:
    # logger.debug("Applying Chemocare transformation")
    _transform_msh_segment(hl7_msg)
    _transform_pid_segment(hl7_msg)
    # logger.debug("Chemocare transformation completed")
    return hl7_msg


def _transform_msh_segment(hl7_msg: Message) -> None:
    msh = hl7_msg.msh

    # MSH.9/MSG.3 = "ADT_A05"
    if hasattr(msh, "msh_9") and msh.msh_9:
        msh.msh_9.msh_9_3 = "ADT_A05"

    # MSH.12/VID.1 = "2.5"
    if hasattr(msh, "msh_12") and msh.msh_12:
        msh.msh_12.msh_12_1 = "2.5"

    # Copy MSH.20 to MSH.21/EI.1 and clear MSH.20
    if hasattr(msh, "msh_20") and msh.msh_20:
        msh20_value = msh.msh_20.value

        if hasattr(msh, "msh_21") and msh.msh_21:
            msh.msh_21.msh_21_1 = msh20_value
        msh.msh_20 = ""

    # Copy MSH.21 to MSH.21/EI.1
    if hasattr(msh, "msh_21") and msh.msh_21:
        msh21_value = msh.msh_21.value
        msh.msh_21.msh_21_1 = msh21_value
        msh.msh_21 = ""


def _transform_pid_segment(hl7_msg: Message) -> None:
    pid = hl7_msg.pid
    msh = hl7_msg.msh

    # Copy PID.2/CX.1 to PID.3/CX.1[1] and clear PID.2/CX.1
    if hasattr(pid, "pid_2") and pid.pid_2:
        pid2_value = pid.pid_2.pid_2_1.value

        # Get MSH.3.1 value
        msh3_value = ""
        if hasattr(msh, "msh_3") and msh.msh_3:
            msh3_value = msh.msh_3.msh_3_1.value if hasattr(msh.msh_3, "msh_3_1") else str(msh.msh_3.value)

        if hasattr(pid, "pid_3") and pid.pid_3:
            # Handle first repetition
            current_pid3_rep1 = pid.pid_3[0].value if pid.pid_3 else ""
            components_rep1 = current_pid3_rep1.split("^")

            # Ensure we have components for first repetition
            while len(components_rep1) < 5:
                components_rep1.append("")

            # Set CX.1 to the PID.2 value
            components_rep1[0] = pid2_value
            # Set CX.4 to "NHS"
            components_rep1[3] = "NHS"
            # Set CX.5 to "NH"
            components_rep1[4] = "NH"

            pid.pid_3[0].value = "^".join(components_rep1)

            # Handle second repetition
            if len(pid.pid_3) > 1:
                current_pid3_rep2 = pid.pid_3[1].value if len(pid.pid_3) > 1 else ""
                components_rep2 = current_pid3_rep2.split("^")

                # Ensure we have components for second repetition
                while len(components_rep2) < 5:
                    components_rep2.append("")

                # Set CX.1 to PID.2 value + MSH.3.1 value
                components_rep2[0] = pid2_value + msh3_value
                # Set CX.4 to MSH.3.1 value directly as HD.1
                components_rep2[3] = msh3_value
                # Set CX.5 to PI
                components_rep2[4] = "PI"

                pid.pid_3[1].value = "^".join(components_rep2)

        pid.pid_2.pid_2_1 = ""

    # Copy PID.32 to PID.31 and clear PID.32
    if hasattr(pid, "pid_32") and pid.pid_32:
        pid32_value = pid.pid_32.value
        if hasattr(pid, "pid_31"):
            pid.pid_31 = pid32_value
        pid.pid_32 = ""


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


hl7_msg = parse_message(message_body)
msh_segment = hl7_msg.msh

print("\nOriginal HL7 Message:")
print("=" * 50)
original_message = hl7_msg.to_er7()
formatted_original = original_message.replace("\r", "\n")
print(formatted_original)
print("=" * 50)

hl7_msg_1 = transform_chemocare(hl7_msg)
updated_message = hl7_msg_1.to_er7()
print("Updated HL7 Message:")
print("=" * 50)
formatted_message = updated_message.replace("\r", "\n")
print(formatted_message)
print("=" * 50)
