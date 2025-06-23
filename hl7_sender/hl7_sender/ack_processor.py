import logging

from hl7apy.core import Message
from hl7apy.parser import parse_message
from message_bus_lib.processing_result import ProcessingResult

logger = logging.getLogger(__name__)

def get_ack_result(response: str) -> ProcessingResult:
    try:
        response_msg: Message = parse_message(response)

        if not response_msg.MSA:
            error = "Received a non-ACK message"
            logger.error(error)
            return ProcessingResult.failed(error, retry=True)

        ack_code = response_msg.MSA.acknowledgment_code.value
        logger.debug(f"ACK Code: {ack_code}")

        if ack_code in ['AA', 'CA']:
            logger.info("Valid ACK received.")
            return ProcessingResult.successful()
        else:
            control_id = response_msg.MSH.message_control_id.value
            error = f"Negative ACK received: {ack_code} for: {control_id}"
            logger.error(error)
            return ProcessingResult.failed(error, retry=True)

    except Exception as e:
        logger.exception("Exception while parsing ACK message")
        return ProcessingResult.failed(f"Exception occurred: {str(e)}", retry=True)
