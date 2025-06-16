import logging

from hl7apy.core import Message
from hl7apy.exceptions import HL7apyException
from hl7apy.mllp import AbstractHandler
from hl7apy.parser import parse_message

from message_bus_lib.message_sender_client import MessageSenderClient
from .hl7_ack_builder import HL7AckBuilder
from message_bus_lib.connection_config import ConnectionConfig
from message_bus_lib.servicebus_client_factory import ServiceBusClientFactory
from message_bus_lib.audit_service_client import AuditServiceClient

# Configure logging
logger = logging.getLogger(__name__)


class GenericHandler(AbstractHandler):

    def __init__(self, msg, sender_client: MessageSenderClient, audit_client: AuditServiceClient):
        super(GenericHandler, self).__init__(msg)
        self.sender_client = sender_client
        self.audit_client = audit_client

    def reply(self) -> str:
        try:
            self.audit_client.log_message_received(self.incoming_message, "Message received successfully")

            msg = parse_message(self.incoming_message, find_groups=False)
            message_control_id = msg.msh.msh_10.value
            message_type = msg.msh.msh_9.to_er7()
            logger.info("Received message type: %s, Control ID: %s", message_type, message_control_id)

            self.audit_client.log_validation_result(
                self.incoming_message,
                f"Valid HL7 message - Type: {message_type}",
                is_success=True
            )

            self._send_to_service_bus(message_control_id)

            ack_message = self.create_ack(message_control_id, msg)

            self.audit_client.log_message_processed(self.incoming_message, "ACK generated successfully")

            logger.info("ACK generated successfully")
            return ack_message
        except HL7apyException as e:
            error_msg = f"HL7 parsing error: {e}"
            logger.error(error_msg)

            self.audit_client.log_validation_result(
                self.incoming_message,
                error_msg,
                is_success=False
            )

            self.audit_client.log_message_failed(self.incoming_message, error_msg)

            raise
        except Exception:
            error_msg = f"Unexpected error while processing message: {e}"
            logger.exception(error_msg)

            self.audit_client.log_message_failed(self.incoming_message, error_msg)
            raise

    def create_ack(self, message_control_id: str, msg: Message) -> str:
        ack_builder = HL7AckBuilder()
        ack_msg = ack_builder.build_ack(message_control_id, msg)
        return ack_msg.to_mllp()

    def _send_to_service_bus(self, message_control_id: str) -> bool:
        try:
            self.sender_client.send_text_message(self.incoming_message)
            logger.info("Message %s sent to Service Bus queue successfully", message_control_id)
        except Exception as e:
            logger.error("Failed to send message %s to Service Bus: %s", message_control_id, str(e))
            raise
