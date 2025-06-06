import logging

from hl7apy.core import Message
from hl7apy.exceptions import HL7apyException
from hl7apy.mllp import AbstractHandler
from hl7apy.parser import parse_message

from .hl7_ack_builder import HL7AckBuilder

# Configure logging
logger = logging.getLogger(__name__)


class GenericHandler(AbstractHandler):
    def reply(self) -> str:
        try:
            msg = parse_message(self.incoming_message, find_groups=False)
            message_control_id = msg.msh.msh_10.value
            message_type = msg.msh.msh_9.to_er7()
            logger.info("Received message type: %s, Control ID: %s", message_type, message_control_id)

            ack_message = self.create_ack(message_control_id, msg)
            logger.info("ACK generated successfully")
            return ack_message
        except HL7apyException as e:
            logger.error("HL7 parsing error: %s", e)
            raise
        except Exception:
            logger.exception("Unexpected error while processing message")
            raise

    def create_ack(self, message_control_id: str, msg: Message) -> str:
        ack_builder = HL7AckBuilder()
        ack_msg = ack_builder.build_ack(message_control_id, msg)
        return ack_msg.to_mllp()
