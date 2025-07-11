import logging

from hl7apy.exceptions import HL7apyException
from hl7apy.parser import parse_message
from message_bus_lib.audit_service_client import AuditServiceClient
from message_bus_lib.message_sender_client import MessageSenderClient

from .base_handler import BaseHandler
from .hl7_validator import HL7Validator, ValidationException

logger = logging.getLogger(__name__)


class ChemocareHandler(BaseHandler):
    """Handles HL7 messages from Chemocare systems with no validation."""

    def __init__(
        self, msg: str, sender_client: MessageSenderClient, audit_client: AuditServiceClient, validator: HL7Validator
    ):
        super().__init__(msg, sender_client, audit_client, validator)

    def reply(self) -> str:
        try:
            self.audit_client.log_message_received(self.incoming_message, "Chemocare message received")

            msg = parse_message(self.incoming_message, find_groups=False)
            message_control_id = msg.msh.msh_10.value if msg.msh.msh_10 else "UNKNOWN"
            message_type = msg.msh.msh_9.to_er7() if msg.msh.msh_9 else "UNKNOWN"
            logger.info("Received Chemocare message type: %s, Control ID: %s", message_type, message_control_id)

            self.audit_client.log_validation_result(
                self.incoming_message,
                f"Chemocare message processed without validation - Type: {message_type}",
                is_success=True,
            )

            # Send to service bus for all messages
            self._send_to_service_bus(message_control_id)

            ack_message = self.create_ack(message_control_id, msg)

            self.audit_client.log_message_processed(self.incoming_message, "Successfully processed Chemocare message")

            logger.info("Chemocare message processed successfully")
            return ack_message

        except HL7apyException as e:
            error_msg = f"HL7 parsing error in Chemocare message: {e}"
            logger.error(error_msg)

            self.audit_client.log_validation_result(self.incoming_message, error_msg, is_success=False)
            self.audit_client.log_message_failed(self.incoming_message, error_msg)
            raise

        except Exception as e:
            error_msg = f"Unexpected error while processing Chemocare message: {e}"
            logger.exception(error_msg)

            self.audit_client.log_message_failed(self.incoming_message, error_msg)
            raise
