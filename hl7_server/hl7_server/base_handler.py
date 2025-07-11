import logging

from hl7apy.core import Message
from hl7apy.mllp import AbstractHandler
from message_bus_lib.audit_service_client import AuditServiceClient
from message_bus_lib.message_sender_client import MessageSenderClient

from .hl7_ack_builder import HL7AckBuilder
from .hl7_validator import HL7Validator

# Configure logging
logger = logging.getLogger(__name__)


class BaseHandler(AbstractHandler):
    def __init__(
        self, msg: str, sender_client: MessageSenderClient, audit_client: AuditServiceClient, validator: HL7Validator
    ):
        super().__init__(msg)
        self.sender_client = sender_client
        self.audit_client = audit_client
        self.validator = validator

    def _send_to_service_bus(self, message_control_id: str) -> None:
        try:
            self.sender_client.send_text_message(self.incoming_message)
            logger.info("Message %s sent to Service Bus queue successfully", message_control_id)
        except Exception as e:
            logger.error("Failed to send message %s to Service Bus: %s", message_control_id, str(e))
            raise

    def create_ack(
        self, message_control_id: str, msg: Message, ack_code: str | None = None, error_text: str | None = None
    ) -> str:
        ack_builder = HL7AckBuilder()
        ack_msg = ack_builder.build_ack(message_control_id, msg, ack_code, error_text)
        return ack_msg.to_mllp()
