import logging

from hl7apy.core import Message
from hl7apy.parser import parse_message

logger = logging.getLogger(__name__)

# ACK codes to indicate successful message
SUCCESS_ACK_CODES = ["AA", "CA"]


def get_ack_result(response: str) -> bool:
    """
    Parses the ACK message and checks if the acknowledgment code indicates success.

    :param response: The ACK message as a string.
    :return: True if the acknowledgment code indicates success, False otherwise.
    """
    try:
        response_message: Message = parse_message(response)

        if not response_message.MSA:
            print("Recieved a non-ACK - message does not contain MSA segment.")
            logger.error("Missing MSA segment.")
            return False

        ack_code = response_message.MSA.acknowledgment_code.value
        logger.debug(f"ACK Code: {ack_code}")

        if ack_code in SUCCESS_ACK_CODES:
            print("Message acknowledged successfully.")
            logger.info("Message acknowledged successfully.")
            return True
        else:
            control_id = response_message.MSA.message_control_id.value
            print(f"Negative ACK Code received: {ack_code}, for message control ID: {control_id}")
            logger.error(f"Negative ACK Code received: {ack_code}, for message control ID: {control_id}")
            return False

    except Exception as e:
        print(f"Error processing ACK message: {e}")
        logger.error(f"Error processing ACK message: {e}")
        return False
