import logging

from event_logger_lib.event_logger import EventLogger
from hl7apy.core import Message
from hl7apy.exceptions import HL7apyException
from hl7apy.mllp import AbstractHandler
from hl7apy.parser import parse_message
from message_bus_lib.message_sender_client import MessageSenderClient

from .hl7_ack_builder import HL7AckBuilder
from .hl7_validator import HL7Validator, ValidationException

# Configure logging
logger = logging.getLogger(__name__)


class GenericHandler(AbstractHandler):
    def __init__(
        self, msg: str, sender_client: MessageSenderClient, event_logger: EventLogger, validator: HL7Validator
    ):
        super(GenericHandler, self).__init__(msg)
        self.sender_client = sender_client
        self.event_logger = event_logger
        self.validator = validator

    def reply(self) -> str:
        try:
            self.event_logger.log_message_received(self.incoming_message)

            msg = parse_message(self.incoming_message, find_groups=False)
            message_control_id = msg.msh.msh_10.value
            message_type = msg.msh.msh_9.to_er7()
            logger.info("Received message type: %s, Control ID: %s", message_type, message_control_id)

            self.validator.validate(msg)
            self.event_logger.log_validation_result(
                self.incoming_message, f"Valid HL7 message - Type: {message_type}", is_success=True
            )

            self._send_to_service_bus(message_control_id)

            ack_message = self.create_ack(message_control_id, msg)

            self.event_logger.log_message_processed(self.incoming_message, "ACK generated successfully")

            logger.info("ACK generated successfully")
            return ack_message
        except HL7apyException as e:
            error_msg = f"HL7 parsing error: {e}"
            logger.error(error_msg)

            self.event_logger.log_validation_result(self.incoming_message, error_msg, is_success=False)
            self.event_logger.log_message_failed(self.incoming_message, error_msg)

            raise
        except ValidationException as e:
            error_msg = f"HL7 validation error: {e}"
            logger.error(error_msg)

            self.event_logger.log_validation_result(self.incoming_message, error_msg, is_success=False)
            self.event_logger.log_message_failed(self.incoming_message, error_msg)
            raise e
        except Exception as e:
            error_msg = f"Unexpected error while processing message: {e}"
            logger.exception(error_msg)

            self.event_logger.log_message_failed(self.incoming_message, error_msg)
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
