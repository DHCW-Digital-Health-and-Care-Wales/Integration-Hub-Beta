from datetime import datetime
import logging
from hl7apy.mllp import AbstractHandler
from hl7apy.parser import parse_message
from hl7apy.exceptions import HL7apyException
from hl7apy.core import Message
from hl7apy.consts import VALIDATION_LEVEL

from hl7_server.dhcw_nhs_wale.hl7_ack_builder import HL7AckBuilder

# Configure logging
logger = logging.getLogger(__name__)


class InvalidHL7FormatException(Exception):
    pass

class GenericHandler(AbstractHandler):

    def reply(self) -> str:
        try:
            if not self.incoming_message.startswith('MSH|^~\\&'):
                logger.warning("Message rejected: not in ER7 (pipe and hat) format")
                raise InvalidHL7FormatException("Invalid HL7 format: expected pipe-and-hat (ER7) format.")

            msg = parse_message(self.incoming_message,find_groups=False)
            message_control_id = msg.msh.msh_10.value
            message_type = msg.msh.msh_9.to_er7()
            logger.info("Received message type: %s, Control ID: %s", message_type, message_control_id)

            if message_type not in ["ADT^A28^ADT_A05", "ADT^A31^ADT_A05"]:
               raise Exception(f"Unsupported message type: {message_type}")
            ack_message = self.create_ack(message_control_id)
            logger.info("ACK generated successfully")
            return ack_message
        except HL7apyException as e:
            logger.error("HL7 parsing error: %s", e)
            raise
        except Exception as e:
            logger.exception("Unexpected error while processing message")
            raise


    def create_ack(self, message_control_id: str) -> str:
        ack_builder = HL7AckBuilder()
        ack_msg = ack_builder.build_ack(message_control_id)
        return ack_builder.to_mllp(ack_msg)

