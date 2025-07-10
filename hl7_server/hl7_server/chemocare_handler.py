import logging

from hl7apy.core import Message
from hl7apy.exceptions import HL7apyException
from hl7apy.parser import parse_message
from message_bus_lib.audit_service_client import AuditServiceClient
from message_bus_lib.message_sender_client import MessageSenderClient

from .chemocare_validator import ChemocareValidator
from .generic_handler import GenericHandler
from .hl7_ack_builder import HL7AckBuilder
from .hl7_constant import Hl7Constants
from .hl7_validator import HL7Validator, ValidationException

logger = logging.getLogger(__name__)


class ChemocareHandler(GenericHandler):
    """Handles HL7 messages from Chemocare systems with specific validation and response logic."""

    def __init__(
        self, msg: str, sender_client: MessageSenderClient, audit_client: AuditServiceClient, validator: HL7Validator
    ):
        # Initialize parent with the provided validator
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

            # Create successful ACK
            ack_message = self.create_successful_ack(message_control_id, msg)

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

            # Try to create failure ACK if we can parse enough to get control ID
            try:
                msg = parse_message(self.incoming_message, find_groups=False)
                message_control_id = msg.msh.msh_10.value
                return self.create_failure_ack(message_control_id, msg, error_msg)
            except:
                # If we can't parse at all, re-raise the original exception
                raise e

        except ValidationException as e:
            error_msg = f"Chemocare validation error: {e}"
            logger.error(error_msg)

            self.audit_client.log_validation_result(self.incoming_message, error_msg, is_success=False)
            self.audit_client.log_message_failed(self.incoming_message, error_msg)

            # Create failure ACK for validation errors
            try:
                msg = parse_message(self.incoming_message, find_groups=False)
                message_control_id = msg.msh.msh_10.value
                return self.create_failure_ack(message_control_id, msg, error_msg)
            except:
                # If parsing fails, re-raise validation exception
                raise e

        except Exception as e:
            error_msg = f"Unexpected error while processing Chemocare message: {e}"
            logger.exception(error_msg)

            self.audit_client.log_message_failed(self.incoming_message, error_msg)
            # Re-raise exception to be consistent with parent GenericHandler
            raise

    def create_successful_ack(self, message_control_id: str, msg: Message) -> str:
        """Creates a successful ACK response."""
        ack_builder = HL7AckBuilder()
        ack_msg = ack_builder.build_ack(message_control_id, msg, Hl7Constants.ACK_CODE_ACCEPT)
        return ack_msg.to_mllp()

    def create_failure_ack(self, message_control_id: str, msg: Message, error_msg: str) -> str:
        """Creates a failure ACK response."""
        ack_builder = HL7AckBuilder()
        ack_msg = ack_builder.build_ack(message_control_id, msg, Hl7Constants.ACK_CODE_REJECT, error_msg)
        return ack_msg.to_mllp()
