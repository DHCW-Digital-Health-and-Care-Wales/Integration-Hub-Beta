"""
=============================================================================
ACK Processor - Week 3 Training
=============================================================================

This module validates HL7 ACK (Acknowledgment) messages to determine
if a sent message was successfully received.

PRODUCTION REFERENCE:
--------------------
See hl7_sender/ack_processor.py for the production version which includes:
- Integration with event logging
- More detailed error reporting
"""

import logging

from hl7apy.core import Message
from hl7apy.parser import parse_message

logger = logging.getLogger(__name__)

# ACK codes that indicate successful message delivery
SUCCESS_ACK_CODES = ["AA", "CA"]


def get_ack_result(response: str) -> bool:
    """
    Validate an HL7 ACK response message.

    This function parses the ACK response and checks the acknowledgment
    code in the MSA segment to determine if the message was accepted.

    Args:
        response: The raw HL7 ACK message as a string

    Returns:
        True if the ACK indicates success (AA or CA)
        False otherwise (error, reject, or invalid message)

    Example:
        >>> ack_msg = "MSH|^~\\&|...|ACK|...\\rMSA|AA|12345|"
        >>> get_ack_result(ack_msg)
        True

    Note:
        This function never raises exceptions - it returns False for any
        invalid or unparseable message. This is intentional for robustness.
    """
    try:
        # Parse the ACK message
        response_msg: Message = parse_message(response)

        # Check that this is actually an ACK message (has MSA segment)
        if not response_msg.MSA:
            print("Received a non-ACK message (no MSA segment)")
            logger.error("Received a non-ACK message")
            return False

        # Get the acknowledgment code from MSA-1
        ack_code = response_msg.MSA.acknowledgment_code.value
        logger.debug(f"ACK Code: {ack_code}")

        # Check if it's a success code
        if ack_code in SUCCESS_ACK_CODES:
            print(f"Valid ACK received: {ack_code}")
            logger.info("Valid ACK received.")
            return True
        else:
            # It's an error or reject code
            control_id = response_msg.MSH.message_control_id.value
            print(f"Negative ACK received: {ack_code} for message: {control_id}")
            logger.error(f"Negative ACK received: {ack_code} for: {control_id}")
            return False

    except Exception as e:
        # If we can't parse the response at all, treat it as a failure
        print(f"Exception while parsing ACK message: {e}")
        logger.exception("Exception while parsing ACK message")
        return False
