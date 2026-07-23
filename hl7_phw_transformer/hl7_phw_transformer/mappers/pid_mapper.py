from field_utils_lib import copy_segment_fields_in_range, get_hl7_field_value
from hl7apy.core import Message

from ..date_of_death_transformer import transform_date_of_death


def map_pid(original_msg: Message, new_msg: Message) -> tuple[str, str] | None:
    segment_names = [s.name for s in original_msg.children]
    if "PID" not in segment_names:
        return None

    pid_segment = original_msg.pid
    new_pid = new_msg.add_segment("PID")

    # Copy all PID fields except PID.3 (conditional mapping) and PID.29 (conditional transformation).
    copy_segment_fields_in_range(pid_segment, new_pid, "pid", start=1, end=2)
    copy_segment_fields_in_range(pid_segment, new_pid, "pid", start=4, end=28)
    copy_segment_fields_in_range(pid_segment, new_pid, "pid", start=30, end=39)

    pid3_rep1 = new_pid.add_field("pid_3")
    rep1_cx1 = get_hl7_field_value(pid_segment, "pid_3[0].cx_1")
    rep1_cx5 = get_hl7_field_value(pid_segment, "pid_3[0].cx_5")
    if rep1_cx1 and rep1_cx5 == "NI":
        pid3_rep1.cx_1 = rep1_cx1
        pid3_rep1.cx_4.hd_1 = "NHS"
        pid3_rep1.cx_5 = "NH"

    original_pid3_repetitions = getattr(pid_segment, "pid_3", [])
    if len(original_pid3_repetitions) > 1:
        pid3_rep2 = new_pid.add_field("pid_3")
        rep2_cx1 = get_hl7_field_value(pid_segment, "pid_3[1].cx_1")
        rep2_cx5 = get_hl7_field_value(pid_segment, "pid_3[1].cx_5")
        if rep2_cx1 and rep2_cx5 == "PI":
            pid3_rep2.cx_1 = rep2_cx1
            pid3_rep2.cx_4.hd_1 = "103"
            pid3_rep2.cx_5 = "PI"

    dod_field_value = getattr(pid_segment, "pid_29", None)

    if dod_field_value:
        original_dod = get_hl7_field_value(pid_segment, "pid_29.ts_1")
    else:
        original_dod = None

    transformed_dod = transform_date_of_death(original_dod)
    new_pid.pid_29.ts_1 = transformed_dod
    if original_dod and original_dod.strip():
        return (original_dod, transformed_dod)

    return None

