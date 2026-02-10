from typing import Any
from field_utils_lib import get_hl7_field_value, set_nested_field
from hl7apy.core import Message
from hl7apy.core import Segment
from ..utils.remove_timezone_from_datetime import remove_timezone_from_datetime


def map_pid(original_hl7_message: Message, new_message: Message) -> None:
    original_pid = getattr(original_hl7_message, "pid", None)
    if not original_pid:
        return  # No PID segment

    # trigger event for A28 (=A04 originally) specific logic
    # NB! in the original message the message type is A04 before conversion to A28
    # so this is checked instead of relying on the mapping order having converted the message type prior
    msg_trigger_event = get_hl7_field_value(original_hl7_message, "msh.msh_9.msg_2")
    is_a04_message = msg_trigger_event == "A04"
    is_a31_message = msg_trigger_event == "A31"

    pid3_reps = list(original_pid.pid_3)
    nhs_index = None

    if is_a31_message:
        print("Picked A31 message for PID Transformation")
        for index, rep in enumerate(pid3_reps):
            if get_hl7_field_value(rep, "cx_5") == "NH":
                nh_number = get_hl7_field_value(original_pid, f"pid_3[{index}].cx_1")
                print(f"NHS Number {nh_number} on index {index}")
                nhs_index = index
                break
        if nhs_index is None or nhs_index == 0:
            return

        print(f"Original PID.3 repetitions before swap: {len(pid3_reps)}")
        print(pid3_reps[0].cx_1.value)
        print(pid3_reps[nhs_index].cx_1.value)

        # Swap the repetitions in the list
        pid3_reps[0], pid3_reps[nhs_index] = pid3_reps[nhs_index], pid3_reps[0]
    print(f"Original PID.3 repetitions after swap: {len(pid3_reps)}")
    print(pid3_reps[0].cx_1.value)
    print(pid3_reps[nhs_index].cx_1.value)

    # Clear existing PID.3 repetitions and add them back in the new order
    # Only perform reordering if A31 message and NHS index was found
    if is_a31_message and nhs_index is not None:
        reorder_pid3_nh_first(original_hl7_message)
        '''
        original_pid.pid_3 = ""
        for rep in pid3_reps:
            new_rep = original_pid.add_field("pid_3")
            # Copy all subfields from the reordered repetition
            cx_1_value = rep.cx_1.value if hasattr(rep.cx_1, 'value') else rep.cx_1
            if cx_1_value:
                new_rep.cx_1 = cx_1_value
            hd_1_value = rep.cx_4.hd_1.value if hasattr(rep.cx_4.hd_1, 'value') else rep.cx_4.hd_1
            if hd_1_value:
                new_rep.cx_4.hd_1 = hd_1_value
            cx_5_value = rep.cx_5.value if hasattr(rep.cx_5, 'value') else rep.cx_5
            if cx_5_value:
                new_rep.cx_5 = cx_5_value

        '''

    original_pid_3_rep1_cx_1 = get_hl7_field_value(original_pid, "pid_3[0].cx_1")
    pid3_rep1 = new_message.pid.add_field("pid_3")

    # if the cx_1 subfield on pid_3[0] exists and is not empty, and cx_5 is "NI"
    if original_pid_3_rep1_cx_1 and get_hl7_field_value(original_pid, "pid_3[0].cx_5") == "NI":
        # check if the NHS number starts with N3 or N4
        nhs_number_prefix = original_pid_3_rep1_cx_1[:2].upper() if len(original_pid_3_rep1_cx_1) >= 2 else ""
        is_n3_or_n4_prefix = nhs_number_prefix in ["N3", "N4"]

        if is_a04_message:
            if is_n3_or_n4_prefix:
                pid3_rep1.cx_1 = original_pid_3_rep1_cx_1
                pid3_rep1.cx_4.hd_1 = "108"
                pid3_rep1.cx_5 = "LI"
            else:
                pid3_rep1.cx_1 = ""
                pid3_rep1.cx_4.hd_1 = ""
                pid3_rep1.cx_5 = ""
        else:
            # for non-A28(=A04 originally) messages
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

    # PID.7 - remove timezone from timestamp for MPI compatibility
    original_pid7_ts1 = get_hl7_field_value(original_pid, "pid_7.ts_1")
    if original_pid7_ts1:
        new_message.pid.pid_7.ts_1 = remove_timezone_from_datetime(original_pid7_ts1)

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

    # Death date and time: trim at first "+" if length > 6, otherwise set to '""'
    original_pid29_ts1 = get_hl7_field_value(original_pid, "pid_29.ts_1")
    new_message.pid.pid_29.ts_1 = (
        remove_timezone_from_datetime(original_pid29_ts1) if len(original_pid29_ts1) > 6 else '""'
    )
    
    #print(f"Mapped PID segment with {len(new_message.pid.pid_3)} repetitions of PID.3, ")

    #print(f"first repetition PID.3[0].cx_1: {get_hl7_field_value(new_message.pid, 'pid_3[0].cx_1')}, ")



def reorder_pid3_nh_first(msg: Message) -> None:
    """
    Reorder PID-3 repetitions so CX-5 == 'NH' is first.
    Modifies the message in-place.
    """

    original_pid = getattr(msg, "pid", None)
    if not original_pid or not original_pid.pid_3:
        print("PID segment or PID-3 not present")
        return

    # Collect PID-3 repetitions
    pid3_reps = list(original_pid.pid_3)

    # Find NH repetition index
    nh_index = None
    for idx, rep in enumerate(pid3_reps):
        if rep.cx_5.value == "NH":
            nh_index = idx
            break

    # Nothing to do
    if nh_index is None or nh_index == 0:
        print("NH already first or not present")
        return

    # Swap NH to first position
    pid3_reps[0], pid3_reps[nh_index] = pid3_reps[nh_index], pid3_reps[0]

    # Build a NEW PID segment (hl7apy-safe)
    new_pid = Segment("PID", validation_level=original_pid.validation_level)

    # Copy all PID fields except PID-3
    for child in original_pid.children:
        if child.name != "PID_3":
            setattr(new_pid, child.name.lower(), getattr(original_pid, child.name.lower()))

    # Rebuild PID-3 repetitions
    for rep in pid3_reps:
        new_rep = new_pid.add_field("pid_3")
        new_rep.cx_1 = rep.cx_1.value
        if rep.cx_2.value:
            new_rep.cx_2 = rep.cx_2.value
        if rep.cx_3.value:
            new_rep.cx_3 = rep.cx_3.value
        if rep.cx_4.hd_1.value:
            new_rep.cx_4.hd_1 = rep.cx_4.hd_1.value
        new_rep.cx_5 = rep.cx_5.value

    # Replace PID in message by directly assigning it
    msg.pid = new_pid

    print("PID-3 reordered: NH is now first")
    print(f"First repetition PID.3[0].cx_1: {get_hl7_field_value(msg.pid, 'pid_3[0].cx_1')}, cx_5: {get_hl7_field_value(msg.pid, 'pid_3[0].cx_5')}")
    print(f"Second repetition PID.3[1].cx_1: {get_hl7_field_value(msg.pid, 'pid_3[1].cx_1')}, cx_5: {get_hl7_field_value(msg.pid, 'pid_3[1].cx_5')}")
