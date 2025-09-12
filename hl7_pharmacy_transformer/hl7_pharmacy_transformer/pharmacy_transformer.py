from typing import Optional

from hl7apy.core import Message

VALID_ASSIGNING_AUTHORITIES = {
    '108', '109', '110', '111', '126', '131', '139', '140', '149', '170', '169', '310'
}


def validate_assigning_authority(hl7_msg: Message) -> bool:
    try:
        original_pid = getattr(hl7_msg, "pid", None)
        if original_pid is None:
            return False

        pid3 = getattr(original_pid, "pid_3", None)
        if pid3 is None:
            return False

        if hasattr(pid3, '__iter__') and not isinstance(pid3, str):
            pid3_rep = pid3[0] if len(pid3) > 0 else None
        else:
            pid3_rep = pid3

        if pid3_rep is None:
            return False

        cx_4 = getattr(pid3_rep, "cx_4", None)
        if cx_4 is None:
            return False

        hd_1 = getattr(cx_4, "hd_1", None)
        if hd_1 is None or not hasattr(hd_1, "value"):
            return False

        assigning_authority = hd_1.value
        if not assigning_authority:
            return False

        return assigning_authority in VALID_ASSIGNING_AUTHORITIES

    except (AttributeError, IndexError, ValueError, TypeError):
        return False


def transform_pharmacy_message(original_hl7_msg: Message) -> Optional[Message]:
    if not validate_assigning_authority(original_hl7_msg):
        return None

    new_message = Message(version=original_hl7_msg.version)

    for segment_name in original_hl7_msg.segment_names:
        segment = getattr(original_hl7_msg, segment_name, None)
        if segment is not None:
            new_segment = getattr(new_message, segment_name)
            for field_name in segment.field_names:
                field = getattr(segment, field_name, None)
                if field is not None and hasattr(field, 'value'):
                    setattr(new_segment, field_name, field.value)

    return new_message
