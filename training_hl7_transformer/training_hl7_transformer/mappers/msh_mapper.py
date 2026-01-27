"""
MSH Segment Mapper for Training Transformer
============================================

This module demonstrates how to map/transform the MSH (Message Header) segment.
The MSH segment is the first segment in every HL7 message and contains metadata
about the message itself.

LEARNING OBJECTIVES:
-------------------
1. Understand the structure of the MSH segment
2. Learn to use field_utils_lib for copying/reading fields
3. Practice making simple transformations

KEY MSH FIELDS:
--------------
MSH-3:  Sending Application - identifies the source system
MSH-4:  Sending Facility - the organization/hospital sending
MSH-5:  Receiving Application - the target system
MSH-6:  Receiving Facility - the receiving organization
MSH-7:  Date/Time of Message - when the message was created
MSH-9:  Message Type - e.g., "ADT^A31" (Patient Update)
MSH-10: Message Control ID - unique identifier for this message
MSH-12: Version ID - HL7 version, e.g., "2.3.1"

PRODUCTION REFERENCE:
--------------------
See hl7_phw_transformer/hl7_phw_transformer/mappers/msh_mapper.py
for a production example that also transforms the datetime format.
"""

from hl7apy.core import Message

# Import field utilities from shared_libs
# These provide helper functions for working with HL7 fields
from field_utils_lib import copy_segment_fields_in_range, get_hl7_field_value
from training_hl7_transformer.datetime_transformer import transform_datetime
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

    created_datetime = get_hl7_field_value(msh_segment, "msh_7.ts_1")
    transformed_datetime = None

    
    if created_datetime:
        transformed_datetime = transform_datetime_to_readable(created_datetime)

        if transformed_datetime and transformed_datetime != created_datetime:
            # Set the transformed datetime on the new message
            new_msh.msh_7.ts_1.value = transformed_datetime
            print(f"MSH-7 transformed: '{created_datetime}' -> '{transformed_datetime}'")
        else:
            print(f"MSH-7 unchanged: '{created_datetime}'")


    # =========================================================================
    # STEP 4: Print transformation details (local logging)
    # =========================================================================
    # In production, we'd use the event_logger library for structured logging.
    # For training, we use print() to see what's happening.
    print("AlexTest")
    print(f"  MSH-3 transformed: '{original_sending_app}' -> '{new_sending_app}'")
    if created_datetime:
            print(
                f"  MSH-7 transformed: '{created_datetime}' -> '{transformed_datetime}'"
            )
    else:
        print("  MSH-7 not present – no datetime transformation applied")    # =========================================================================
    # STEP 5: Return transformation details
    # =========================================================================
    # This dictionary can be used for auditing or testing
    # This dictionary can be used for auditing or testing
    return {
        "original_sending_app": original_sending_app or "",
        "new_sending_app": new_sending_app,
        # WEEK 2 EXERCISE 1 SOLUTION: Include datetime transformation details
        "original_datetime": created_datetime or "",
        "transformed_datetime": transformed_datetime or "",
    }