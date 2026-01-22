"""
===========================================================================
WEEK 2 EXERCISE 3 SOLUTION: PID Segment Mapping with Name Transformation
===========================================================================

This module maps the PID (Patient Identification) segment from original
to new message, with a transformation that converts the patient name to uppercase.

EXERCISE REQUIREMENTS:
---------------------
1. Use bulk copy for all PID fields (there are lots!)
2. Transform patient name (PID-5) to uppercase

PID-5 STRUCTURE (XPN - Extended Person Name):
--------------------------------------------
The patient name field has this structure:
  FAMILY^GIVEN^MIDDLE^SUFFIX^PREFIX^DEGREE

Example: SMITH^JOHN^WILLIAM^^MR^MD
  - Family name:  SMITH
  - Given name:   JOHN
  - Middle name:  WILLIAM
  - Suffix:       (empty)
  - Prefix:       MR
  - Degree:       MD

In hl7apy, you access these as:
  pid.pid_5.xpn_1  -> Family name component
  pid.pid_5.xpn_2  -> Given name component
  etc.

PRODUCTION REFERENCE:
--------------------
See hl7_phw_transformer/hl7_phw_transformer/mappers/pid_mapper.py
for a production example with date format handling.
"""

from field_utils_lib import copy_segment_fields_in_range, get_hl7_field_value
from hl7apy.core import Message


def map_pid(original_msg: Message, new_msg: Message) -> dict[str, str]:
    """
    Map the PID segment from original to new message with name uppercasing.

    This function:
    1. Bulk copies all 39 PID fields
    2. Extracts the patient name components
    3. Converts name to uppercase
    4. Sets the uppercased name on the new message

    Args:
        original_msg: The original parsed HL7 message.
        new_msg: The new message being built.

    Returns:
        A dictionary with transformation details for logging.

    Example:
        >>> msg = parse_message(raw_hl7)
        >>> new_msg = Message(version="2.3.1")
        >>> details = map_pid(msg, new_msg)
        >>> print(details)
        {'original_name': 'Smith^John^William', 'transformed_name': 'SMITH^JOHN^WILLIAM'}
    """
    # =========================================================================
    # Access the PID segments
    # =========================================================================
    original_pid = original_msg.pid
    new_pid = new_msg.pid

    # =========================================================================
    # STEP 1: Bulk copy all PID fields (1-39)
    # =========================================================================
    # PID has up to 39 fields in HL7 v2.5
    # This copies ALL of them in one call
    #
    # Note: After bulk copy, PID-5 contains the original (mixed case) name.
    # To be overriden in Step 3.
    copy_segment_fields_in_range(
        source_segment=original_pid,
        target_segment=new_pid,
        field_prefix="pid",
        start=1,
        end=39,
    )

    # =========================================================================
    # STEP 2: Extract original name components using get_hl7_field_value()
    # =========================================================================
    # get_hl7_field_value() safely extracts values without throwing exceptions
    # If a field doesn't exist, it returns an empty string ""
    #
    # PID-5 structure: FAMILY^GIVEN^MIDDLE^SUFFIX^PREFIX
    # In hl7apy notation:
    #   pid_5.xpn_1 = Family name (FN - Family Name)
    #   pid_5.xpn_2 = Given name
    #   pid_5.xpn_3 = Middle name or initial
    #   pid_5.xpn_4 = Suffix (Jr, Sr, III)
    #   pid_5.xpn_5 = Prefix (Mr, Mrs, Dr)

    # Try the nested FN component first (for complex family name structures)
    original_family = get_hl7_field_value(original_pid, "pid_5.xpn_1.fn_1")
    if not original_family:
        # Fall back to simple xpn_1 if FN component isn't used
        original_family = get_hl7_field_value(original_pid, "pid_5.xpn_1")

    original_given = get_hl7_field_value(original_pid, "pid_5.xpn_2")
    original_middle = get_hl7_field_value(original_pid, "pid_5.xpn_3")

    # Build original name string for logging - entirely optional
    original_name_parts = [p for p in [original_family, original_given, original_middle] if p]
    original_name = "^".join(original_name_parts)

    # =========================================================================
    # STEP 3: Transform name to UPPERCASE uding .upper()
    # =========================================================================
    # We apply this to each name component individually

    if original_family:
        # Access the XPN component and set the uppercase value
        # Note: We need to check if we're dealing with FN subcomponent or direct value
        try:
            new_pid.pid_5.xpn_1.fn_1.value = original_family.upper()
        except AttributeError:
            # If FN component doesn't exist, set xpn_1 directly
            new_pid.pid_5.xpn_1.value = original_family.upper()

    if original_given:
        new_pid.pid_5.xpn_2.value = original_given.upper()

    if original_middle:
        new_pid.pid_5.xpn_3.value = original_middle.upper()

    # Build transformed name string for logging
    transformed_name_parts = [p.upper() for p in original_name_parts]
    transformed_name = "^".join(transformed_name_parts)

    # =========================================================================
    # STEP 4: Print transformation details
    # =========================================================================
    if original_name:
        print(f"PID-5 transformed: '{original_name}' -> '{transformed_name}'")
    else:
        print("PID segment copied (no patient name to transform)")

    # =========================================================================
    # STEP 5: Return transformation details
    # =========================================================================
    return {
        "original_name": original_name,
        "transformed_name": transformed_name,
    }
