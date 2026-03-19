"""
===========================================================================
WEEK 2 EXERCISE 2 SOLUTION: EVN Segment Mapping
===========================================================================

This module maps the EVN (Event Type) segment from original to new message.

EXERCISE REQUIREMENTS:
---------------------
Copy EVN segment from original to transformed message using bulk copy.

EXAMPLE EVN SEGMENT:
-------------------
EVN||20260122143055|||USER001

PRODUCTION REFERENCE:
--------------------
See hl7_pims_transformer/hl7_pims_transformer/mappers/evn_mapper.py
for a production example with timezone handling.
"""

from field_utils_lib import copy_segment_fields_in_range, get_hl7_field_value
from hl7apy.core import Message


def map_evn(original_msg: Message, new_msg: Message) -> dict[str, str]:
    """
    Map the EVN segment from original to new message.

    This function performs a bulk copy of all EVN fields (1-7).
    Unlike the MSH mapper, we don't apply any transformations here -
    just a straightforward copy.

    Args:
        original_msg: The original parsed HL7 message.
        new_msg: The new message being built.

    Returns:
        A dictionary with EVN segment details for logging.

    Raises:
        AttributeError: If the original message doesn't have an EVN segment.
                       (In practice, we handle this gracefully)

    Example:
        >>> msg = parse_message(raw_hl7)
        >>> new_msg = Message(version="2.3.1")
        >>> details = map_evn(msg, new_msg)
        >>> print(details)
        {'evn_2': '20260122143055', 'evn_5': 'USER001'}
    """
    # =========================================================================
    # Access the EVN segments
    # =========================================================================
    # Note: This will raise AttributeError if EVN doesn't exist.
    # In production, you might want to check first:
    #   if not hasattr(original_msg, 'evn') or original_msg.evn is None:
    original_evn = original_msg.evn
    new_evn = new_msg.evn

    # =========================================================================
    # BULK COPY: Copy all EVN fields (1-7)
    # =========================================================================
    # The EVN segment has up to 7 fields in HL7 v2.5
    # For v2.3.1, it typically has 6 fields, but copying 1-7 is safe
    # (missing fields are simply not copied)
    #
    # This is the key function from field_utils_lib:
    # - Iterates through fields 1 to 7
    # - For each field, copies the value from original to new
    # - Handles missing fields gracefully (skips them)
    copy_segment_fields_in_range(
        source_segment=original_evn,
        target_segment=new_evn,
        field_prefix="evn",
        start=1,
        end=7,
    )

    # =========================================================================
    # Extract key values for logging
    # =========================================================================
    # We return the most commonly used EVN fields for audit purposes
    evn_2 = get_hl7_field_value(original_evn, "evn_2.ts_1") or get_hl7_field_value(original_evn, "evn_2")
    evn_5 = get_hl7_field_value(original_evn, "evn_5")

    print(f"  EVN segment copied (Recorded DateTime: {evn_2 or '(empty)'})")

    return {
        "evn_2_recorded_datetime": evn_2 or "",
        "evn_5_operator_id": evn_5 or "",
    }
