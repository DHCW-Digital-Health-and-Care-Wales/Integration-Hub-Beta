import logging

from hl7apy.consts import VALIDATION_LEVEL
from hl7apy.core import Message
from hl7apy.parser import parse_message

logger = logging.getLogger(__name__)

def get_ack_result(response: str) -> bool:
    try:
        # The MSH segment is the first line of the message
        lines = response.splitlines()
        if not lines:
            logger.error("Received an empty response.")
            return False

        msh_segment = lines[0]
        logger.info(f"Received {msh_segment}")

        fields = msh_segment.split('|')
        # MSH.9 is at index 8 (0-based)
        if len(fields) > 8:
            msh_9 = fields[8]
            components = msh_9.split('^')
            # If we have ACK^Axx but not ACK^Axx^ACK, append ACK
            if len(components) == 2 and components[0] == 'ACK':
                logger.warning("Incomplete MSH.9 found. Appending '^ACK' to message type.")
                fields[8] = f"{msh_9}^ACK"
                lines[0] = '|'.join(fields)
                response = '\r'.join(lines)

        response_msg: Message = parse_message(response, validation_level=VALIDATION_LEVEL.TOLERANT)

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

    except Exception as e:
        logger.exception("Exception while parsing ACK message: %s", e)
        return False
