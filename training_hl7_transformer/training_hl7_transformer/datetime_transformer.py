"""
===========================================================================
WEEK 2 EXERCISE 1 SOLUTION: DateTime Transformation
===========================================================================

This module transforms HL7 datetime formats between different representations.

EXERCISE REQUIREMENTS:
---------------------
Transform MSH-7 (Message DateTime) from "YYYYMMDDHHMMSS" to "YYYY-MM-DD HH:MM:SS"

FORMATS:
------------------
- Input format:  "YYYYMMDDHHMMSS"     (e.g., "20260122143055")
- Output format: "YYYY-MM-DD HH:MM:SS" (e.g., "2026-01-22 14:30:55")

PRODUCTION REFERENCE:
--------------------
See hl7_phw_transformer/hl7_phw_transformer/datetime_transformer.py
for a production example (note: it does the REVERSE transformation!).
"""

from datetime import datetime


def transform_datetime_to_readable(date_time: str) -> str | None:
    """
    Transform datetime from HL7 compact format to human-readable format.

    This function demonstrates the OPPOSITE of what the PHW transformer does.
    PHW converts readable -> compact, we convert compact -> readable.

    Args:
        date_time: Datetime string in YYYYMMDDHHMMSS format (e.g., "20260122143055")

    Returns:
        Datetime string in YYYY-MM-DD HH:MM:SS format (e.g., "2026-01-22 14:30:55")
        Returns None if input is empty or None

    Raises:
        ValueError: If the input string doesn't match expected format

    Example:
        >>> transform_datetime_to_readable("20260122143055")
        '2026-01-22 14:30:55'

        >>> transform_datetime_to_readable("")
        None
    """
    # =========================================================================
    # Handle empty or None input
    # =========================================================================
    if not date_time:
        return None

    # =========================================================================
    # Define the format strings
    # =========================================================================
    # strptime format codes:
    #   %Y = 4-digit year
    #   %m = 2-digit month (01-12)
    #   %d = 2-digit day (01-31)
    #   %H = 2-digit hour (00-23)
    #   %M = 2-digit minute (00-59)
    #   %S = 2-digit second (00-59)

    hl7_format = "%Y%m%d%H%M%S"  # Input: YYYYMMDDHHMMSS
    readable_format = "%Y-%m-%d %H:%M:%S"  # Output: YYYY-MM-DD HH:MM:SS

    # =========================================================================
    # Check if already in readable format - If the datetime already has dashes/colons
    # =========================================================================
    try:
        datetime.strptime(date_time, readable_format)
        # Already in readable format - return as-is
        return date_time
    except ValueError:
        pass  # Not in readable format, continue with transformation

    # =========================================================================
    # Parse the HL7 compact format
    # =========================================================================
    # strptime converts string to datetime object
    try:
        dt = datetime.strptime(date_time, hl7_format)
    except ValueError as e:
        # Log the error and re-raise with more context
        print(f"Failed to parse datetime '{date_time}': {e}")
        raise ValueError(f"Cannot parse datetime '{date_time}' - expected format YYYYMMDDHHMMSS") from e

    # =========================================================================
    # Format to human-readable string
    # =========================================================================
    # strftime converts datetime object to string
    result = dt.strftime(readable_format)

    return result


def transform_datetime_to_hl7(date_time: str) -> str | None:
    """
    Transform datetime from human-readable format to HL7 compact format.

    This is the REVERSE of transform_datetime_to_readable().
    This is what the production PHW transformer does.

    Args:
        date_time: Datetime string in YYYY-MM-DD HH:MM:SS format

    Returns:
        Datetime string in YYYYMMDDHHMMSS format
        Returns None if input is empty or None

    Example:
        >>> transform_datetime_to_hl7("2026-01-22 14:30:55")
        '20260122143055'
    """
    if not date_time:
        return None

    hl7_format = "%Y%m%d%H%M%S"
    readable_format = "%Y-%m-%d %H:%M:%S"

    # Check if already in HL7 format
    try:
        datetime.strptime(date_time, hl7_format)
        return date_time  # Already in HL7 format
    except ValueError:
        pass

    # Parse readable format and convert to HL7 format
    dt = datetime.strptime(date_time, readable_format)
    return dt.strftime(hl7_format)
