import logging

from hl7_validation import (
    XmlValidationError,
    validate_er7_with_flow,
)
from hl7apy.core import Message
from hl7apy.exceptions import HL7apyException
from hl7apy.mllp import AbstractHandler
from hl7apy.parser import parse_message
from message_bus_lib.audit_service_client import AuditServiceClient
from message_bus_lib.message_sender_client import MessageSenderClient

from .hl7_ack_builder import HL7AckBuilder
from .hl7_validator import HL7Validator, ValidationException

logger = logging.getLogger(__name__)


class GenericHandler(AbstractHandler):
    def __init__(
        self,
        msg: str,
        sender_client: MessageSenderClient,
        audit_client: AuditServiceClient,
        validator: HL7Validator,
        flow_name: str | None = None,
    ):
        super(GenericHandler, self).__init__(msg)
        self.sender_client = sender_client
        self.audit_client = audit_client
        self.validator = validator
        self.flow_name: str | None = flow_name

    def reply(self) -> str:
        try:
            self.audit_client.log_message_received(self.incoming_message, "Message received successfully")

            msg = parse_message(self.incoming_message, find_groups=False)
            message_control_id = msg.msh.msh_10.value
            message_type = msg.msh.msh_9.to_er7()
            logger.info("Received message type: %s, Control ID: %s", message_type, message_control_id)

            self.validator.validate(msg)
            self.audit_client.log_validation_result(
                self.incoming_message, f"Valid HL7 message - Type: {message_type}", is_success=True
            )

            if self.flow_name:
                try:
                    validate_er7_with_flow(self.incoming_message, self.flow_name)
                    self.audit_client.log_validation_result(
                        self.incoming_message,
                        f"XML validation passed for flow '{self.flow_name}'",
                        is_success=True,
                    )
                except XmlValidationError as e:
                    error_msg = f"XML validation failed for flow '{self.flow_name}': {e}"
                    logger.error(error_msg)
                    self.audit_client.log_validation_result(self.incoming_message, error_msg, is_success=False)
                    self.audit_client.log_message_failed(
                        self.incoming_message, error_msg, "XML schema validation failed"
                    )
                    raise

            self._send_to_service_bus(message_control_id)

            ack_message = self.create_ack(message_control_id, msg)

            self.audit_client.log_message_processed(self.incoming_message, "ACK generated successfully")

            logger.info("ACK generated successfully")
            return ack_message
        except HL7apyException as e:
            error_msg = f"HL7 parsing error: {e}"
            logger.error(error_msg)

            self.audit_client.log_validation_result(self.incoming_message, error_msg, is_success=False)
            self.audit_client.log_message_failed(self.incoming_message, error_msg)

            raise
        except ValidationException as e:
            error_msg = f"HL7 validation error: {e}"
            logger.error(error_msg)

            self.audit_client.log_validation_result(self.incoming_message, error_msg, is_success=False)
            self.audit_client.log_message_failed(self.incoming_message, error_msg)
            raise e
        except Exception as e:
            error_msg = f"Unexpected error while processing message: {e}"
            logger.exception(error_msg)

            self.audit_client.log_message_failed(self.incoming_message, error_msg)
            raise

    def create_ack(self, message_control_id: str, msg: Message) -> str:
        ack_builder = HL7AckBuilder()
        ack_msg = ack_builder.build_ack(message_control_id, msg)
        return ack_msg.to_mllp()

    def _send_to_service_bus(self, message_control_id: str) -> None:
        try:
            self.sender_client.send_text_message(self.incoming_message)
            logger.info("Message %s sent to Service Bus queue successfully", message_control_id)
        except Exception as e:
            logger.error("Failed to send message %s to Service Bus: %s", message_control_id, str(e))
            raise
