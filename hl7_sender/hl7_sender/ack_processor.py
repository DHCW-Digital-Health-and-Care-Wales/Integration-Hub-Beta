import logging

from hl7apy.core import Message
from hl7apy.parser import parse_message

logger = logging.getLogger(__name__)

def get_ack_result(response: str) -> bool:
    try:
        response_msg: Message = parse_message(response)

        if not response_msg.MSA:
            error = "Received a non-ACK message"
            logger.error(error)
            return False

        ack_code = response_msg.MSA.acknowledgment_code.value
        logger.debug(f"ACK Code: {ack_code}")

        if ack_code in ['AA', 'CA']:
            logger.info("Valid ACK received.")
            return True
        else:
            control_id = response_msg.MSH.message_control_id.value
            error = f"Negative ACK received: {ack_code} for: {control_id}"
            logger.error(error)
            return False

    except Exception:
        logger.exception('Exception while parsing ACK message')
        return False
