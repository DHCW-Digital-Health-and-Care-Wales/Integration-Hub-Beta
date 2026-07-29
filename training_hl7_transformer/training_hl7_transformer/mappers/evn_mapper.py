"""
EVN Segment Mapper for Training Transformer
============================================

This module demonstrates how to map/transform the EVN (Event Type) segment.
The EVN segment contains metadata about the event described in the HL7 message.

"""

from datetime import datetime

from hl7apy.core import Message

# Import field utilities from shared_libs
# These provide helper functions for working with HL7 fields
from field_utils_lib import copy_segment_fields_in_range, get_hl7_field_value


def map_evn(original_msg: Message, new_msg: Message) -> None:
    """
    Map the EVN segment from original to new message.

    This function copies all EVN fields and applies transformations:
    1. Copies all standard EVN fields (EVN-1 through EVN-10)

    Args:
        original_msg: The original parsed HL7 message.
        new_msg: The new message being built.

    Returns:
        Nothing

    """
    # =========================================================================
    # Access the EVN segments from both messages
    # =========================================================================
    evn_segment = original_msg.evn
    new_evn = new_msg.evn

    # =========================================================================
    # STEP 1: Copy all standard EVN fields
    # =========================================================================
    # The copy_segment_fields_in_range function copies fields from the original
    # segment to the new segment. We copy EVN-1 through EVN-10.
    #
    # Production Reference:
    # See field_utils_lib/field_utils_lib/field_utils.py for implementation
    copy_segment_fields_in_range(evn_segment, new_evn, "evn", start=1, end=2)


    # =========================================================================
    # STEP 5: Return transformation details
    # =========================================================================
    # This dictionary can be used for auditing or testing
    return None
