import logging

from hl7apy.exceptions import HL7apyException
from hl7apy.parser import parse_message
from message_bus_lib.audit_service_client import AuditServiceClient
from message_bus_lib.message_sender_client import MessageSenderClient

from .base_handler import BaseHandler
from .chemocare_validator import ChemocareValidator
from .hl7_validator import HL7Validator, ValidationException

logger = logging.getLogger(__name__)


class ChemocareHandler(BaseHandler):
    """Handles HL7 messages from Chemocare systems with specific validation and response logic."""

    def __init__(
        self, msg: str, sender_client: MessageSenderClient, audit_client: AuditServiceClient, validator: HL7Validator
    ):
        super().__init__(msg, sender_client, audit_client, validator)
        self.chemocare_validator = ChemocareValidator()

    def reply(self) -> str:
        try:
            self.audit_client.log_message_received(self.incoming_message, "Chemocare message received")

            msg = parse_message(self.incoming_message, find_groups=False)
            message_control_id = msg.msh.msh_10.value
            message_type = msg.msh.msh_9.to_er7()
            logger.info("Received Chemocare message type: %s, Control ID: %s", message_type, message_control_id)

            # Validate using Chemocare-specific validator
            authority_code = self.chemocare_validator.validate(msg)
            health_board_name = self.chemocare_validator.get_health_board_name(authority_code)

            self.audit_client.log_validation_result(
                self.incoming_message,
                f"Valid Chemocare message from {health_board_name} - Type: {message_type}",
                is_success=True,
            )

            # Send to service bus for valid messages
            self._send_to_service_bus(message_control_id)

            ack_message = self.create_ack(message_control_id, msg)

            self.audit_client.log_message_processed(
                self.incoming_message, f"Successfully processed Chemocare message from {health_board_name}"
            )

            logger.info("Chemocare message processed successfully for %s", health_board_name)
            return ack_message

        except HL7apyException as e:
            error_msg = f"HL7 parsing error in Chemocare message: {e}"
            logger.error(error_msg)

            self.audit_client.log_validation_result(self.incoming_message, error_msg, is_success=False)
            self.audit_client.log_message_failed(self.incoming_message, error_msg)
            raise

        except ValidationException as e:
            error_msg = f"Chemocare validation error: {e}"
            logger.error(error_msg)

            self.audit_client.log_validation_result(self.incoming_message, error_msg, is_success=False)
            self.audit_client.log_message_failed(self.incoming_message, error_msg)
            raise e

        except Exception as e:
            error_msg = f"Unexpected error while processing Chemocare message: {e}"
            logger.exception(error_msg)

            self.audit_client.log_message_failed(self.incoming_message, error_msg)
            raise
