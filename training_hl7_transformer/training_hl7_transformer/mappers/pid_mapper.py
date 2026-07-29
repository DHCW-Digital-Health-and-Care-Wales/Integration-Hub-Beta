"""
PID Segment Mapper for Training Transformer
============================================

This module demonstrates how to map/transform the PID (Patient Identification) segment.
The PID segment contains patient demographic information.

"""

from datetime import datetime

from hl7apy.core import Message

# Import field utilities from shared_libs
# These provide helper functions for working with HL7 fields
from field_utils_lib import copy_segment_fields_in_range, get_hl7_field_value


def map_pid(original_msg: Message, new_msg: Message) -> dict[str, str]:
    """
    Map the PID segment from original to new message.

    This function copies all PID fields and applies transformations:
    1. Copies all standard PID fields (PID-3 through PID-21)
    2. Changes the Patient Name (PID-5) to Uppercase
    3. Returns transformation details for logging

    Args:
        original_msg: The original parsed HL7 message.
        new_msg: The new message being built.

    Returns:
        A dictionary with transformation details for logging.
        Keys: original_name, new_name

    """
    # =========================================================================
    # Access the PID segments from both messages
    # =========================================================================
    pid_segment = original_msg.pid
    new_pid = new_msg.pid

    # =========================================================================
    # STEP 1: Copy all standard PID fields
    # =========================================================================
    # The copy_segment_fields_in_range function copies fields from the original
    # segment to the new segment. We copy PID-3 through PID-21.
    #
    # Why start at 3?
    # - MSH-1 (Field Separator) is always "|" and is set automatically
    # - MSH-2 (Encoding Characters) is always "^~\&" and is set automatically
    #
    # Production Reference:
    # See field_utils_lib/field_utils_lib/field_utils.py for implementation
    copy_segment_fields_in_range(pid_segment, new_pid, "pid", start=3, end=21)

    # =========================================================================
    # STEP 2: Get the original patient name
    # =========================================================================
    # MSH-3 contains the Sending Application code
    # We'll record this before transforming for our audit trail
    original_name = get_hl7_field_value(pid_segment, "pid_5")

    # =========================================================================
    # STEP 3: Transform the Patient Name
    # =========================================================================
    # This is our simple training transformation:
    # We change PID-5 to uppercase to indicate transformation.
    #
    # In production, you might:
    # - Map source system codes to target system codes
    # - Add a suffix to indicate transformation applied
    # - Change datetime formats (see PHW transformer)
    new_name = original_name.upper()
    new_pid.pid_5.value = new_name

    # =========================================================================
    # STEP 4: Print transformation details (local logging)
    # =========================================================================
    # In production, we'd use the event_logger library for structured logging.
    # For training, we use print() to see what's happening.
    print(f"  PID-5 transformed: '{original_name}' -> '{new_name}'")

    # =========================================================================
    # STEP 5: Return transformation details
    # =========================================================================
    # This dictionary can be used for auditing or testing
    return {
        "original_name": original_name or "",
        "new_name": new_name or "",
    }
