"""
MSH Segment Mapper for Training Transformer
============================================

This module demonstrates how to map/transform the MSH (Message Header) segment.
The MSH segment is the first segment in every HL7 message and contains metadata
about the message itself.

PRODUCTION REFERENCE:
--------------------
See hl7_phw_transformer/hl7_phw_transformer/mappers/msh_mapper.py
for a production example that also transforms the datetime format.

===========================================================================
WEEK 2 EXERCISE 1 SOLUTION: DateTime Transformation
===========================================================================
This mapper now includes datetime transformation for MSH-7.
See the transform_datetime_to_readable() function imported from datetime_transformer.py
"""

from field_utils_lib import copy_segment_fields_in_range, get_hl7_field_value
from hl7apy.core import Message

# ===========================================================================
# WEEK 2 EXERCISE 1 SOLUTION: Import datetime transformer
# ===========================================================================
from training_hl7_transformer.datetime_transformer import transform_datetime_to_readable


def map_msh(original_msg: Message, new_msg: Message) -> dict[str, str]:
    """
    Map the MSH segment from original to new message.

    This function copies all MSH fields and applies transformations:
    1. Copies all standard MSH fields (MSH-3 through MSH-21)
    2. Changes the Sending Application (MSH-3) to "TRAINING_TRANSFORMER"
    3. Returns transformation details for logging

    IMPORTANT: In production transformers, this function often transforms
    datetime formats, changes receiving application codes, or modifies
    version IDs. For training, we do a simple sender rename.

    Args:
        original_msg: The original parsed HL7 message.
        new_msg: The new message being built.

    Returns:
        A dictionary with transformation details for logging.
        Keys: original_sending_app, new_sending_app

    Example:
        >>> msg = parse_message(raw_hl7)
        >>> new_msg = Message(version="2.3.1")
        >>> details = map_msh(msg, new_msg)
        >>> print(details)
        {'original_sending_app': '169', 'new_sending_app': 'TRAINING_TRANSFORMER'}
    """
    # =========================================================================
    # Access the MSH segments from both messages
    # =========================================================================
    msh_segment = original_msg.msh
    new_msh = new_msg.msh

    # =========================================================================
    # STEP 1: Copy all standard MSH fields
    # =========================================================================
    # The copy_segment_fields_in_range function copies fields from the original
    # segment to the new segment. We copy MSH-3 through MSH-21.
    #
    # Why start at 3?
    # - MSH-1 (Field Separator) is always "|" and is set automatically
    # - MSH-2 (Encoding Characters) is always "^~\&" and is set automatically
    #
    # Production Reference:
    # See field_utils_lib/field_utils_lib/field_utils.py for implementation
    copy_segment_fields_in_range(msh_segment, new_msh, "msh", start=3, end=21)

    # =========================================================================
    # STEP 2: Get the original sending application
    # =========================================================================
    # MSH-3 contains the Sending Application code
    # We'll record this before transforming for our audit trail
    original_sending_app = get_hl7_field_value(msh_segment, "msh_3")

    # =========================================================================
    # STEP 3: Transform the Sending Application
    # =========================================================================
    # This is our simple training transformation:
    # We change MSH-3 to identify that this message has been processed
    # by the training transformer.
    #
    # In production, you might:
    # - Map source system codes to target system codes
    # - Add a suffix to indicate transformation applied
    # - Change datetime formats (see PHW transformer)
    new_sending_app = "TRAINING_TRANSFORMER"
    new_msh.msh_3.value = new_sending_app

    # =========================================================================
    # WEEK 2 EXERCISE 1 SOLUTION: Transform MSH-7 DateTime
    # =========================================================================
    # MSH-7 contains the message creation datetime
    # We transform from compact HL7 format (YYYYMMDDHHMMSS) to readable format
    #
    # Get the original datetime value from MSH-7.TS-1 (timestamp component 1)
    original_datetime = get_hl7_field_value(msh_segment, "msh_7.ts_1")
    transformed_datetime = None

    if original_datetime:
        # Apply datetime transformation
        transformed_datetime = transform_datetime_to_readable(original_datetime)

        if transformed_datetime and transformed_datetime != original_datetime:
            # Set the transformed datetime on the new message
            new_msh.msh_7.ts_1.value = transformed_datetime
            print(f"MSH-7 transformed: '{original_datetime}' -> '{transformed_datetime}'")
        else:
            print(f"MSH-7 unchanged: '{original_datetime}'")

    # =========================================================================
    # STEP 4: Print transformation details (local logging)
    # =========================================================================
    # In production, we'd use the event_logger library for structured logging.
    # For training, we use print() to see what's happening.
    print(f"MSH-3 transformed: '{original_sending_app}' -> '{new_sending_app}'")

    # =========================================================================
    # STEP 5: Return transformation details
    # =========================================================================
    # This dictionary can be used for auditing or testing
    return {
        "original_sending_app": original_sending_app or "",
        "new_sending_app": new_sending_app,
        # WEEK 2 EXERCISE 1 SOLUTION: Include datetime transformation details
        "original_datetime": original_datetime or "",
        "transformed_datetime": transformed_datetime or "",
    }
