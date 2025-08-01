import logging

from hl7apy.core import Message
from hl7apy.exceptions import HL7apyException
from hl7apy.mllp import AbstractHandler
from hl7apy.parser import parse_message
from message_bus_lib.message_sender_client import MessageSenderClient

from .hl7_ack_builder import build_ack, build_nack

# Configure logging
logger = logging.getLogger(__name__)


class GenericHandler(AbstractHandler):

    def __init__(self, msg: Message, sender_client: MessageSenderClient):
        super(GenericHandler, self).__init__(msg)
        self.sender_client = sender_client

    def reply(self) -> str:
        try:
            logger.info("Received message: %s", self.incoming_message)
            msg = parse_message(self.incoming_message, find_groups=False)
            message_control_id = msg.msh.msh_10.value
            message_type = msg.msh.msh_9.to_er7()
            logger.info("Received message type: %s, Control ID: %s", message_type, message_control_id)

            self._send_to_service_bus(message_control_id)

            negative_ack = "fail" in self.incoming_message.lower()
            ack_message = self.create_ack(message_control_id, msg, negative_ack)
            logger.info(f"{"N" if negative_ack else ""}ACK generated successfully")
            return ack_message
        except HL7apyException as e:
            logger.error("HL7 parsing error: %s", e)
            raise
        except Exception:
            logger.exception("Unexpected error while processing message")
            raise

    def create_ack(self, message_control_id: str, msg: Message, negative_ack: bool = False) -> str:
        ack_msg = build_nack(message_control_id, msg) if negative_ack else build_ack(message_control_id, msg)
        return ack_msg.to_mllp()

    def _send_to_service_bus(self, message_control_id: str) -> None:
        try:
            self.sender_client.send_text_message(self.incoming_message)
            logger.info("Message %s sent to Service Bus queue successfully", message_control_id)
        except Exception as e:
            logger.error("Failed to send message %s to Service Bus: %s", message_control_id, str(e))
            raise
