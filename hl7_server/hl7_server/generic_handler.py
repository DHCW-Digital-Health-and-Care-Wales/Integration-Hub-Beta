import logging

from event_logger_lib.event_logger import EventLogger
from hl7_validation import (
    XmlValidationError,
    validate_parsed_message_with_flow_schema,
    validate_parsed_message_with_standard,
)
from hl7apy.core import Message
from hl7apy.exceptions import HL7apyException
from hl7apy.mllp import AbstractHandler
from hl7apy.parser import parse_message
from message_bus_lib.message_sender_client import MessageSenderClient
from message_bus_lib.metadata_utils import get_metadata_log_values
from metric_sender_lib.metric_sender import MetricSender

from hl7_server.custom_message_properties import FLOW_PROPERTY_BUILDERS, build_common_properties

from .hl7_ack_builder import HL7AckBuilder
from .hl7_validator import HL7Validator, ValidationException

logger = logging.getLogger(__name__)


class GenericHandler(AbstractHandler):
    def __init__(
        self,
        msg: str,
        sender_client: MessageSenderClient,
        event_logger: EventLogger,
        metric_sender: MetricSender,
        validator: HL7Validator,
        workflow_id: str,
        sending_app: str | None,
        flow_name: str | None = None,
        standard_version: str | None = None,
    ):
        super(GenericHandler, self).__init__(msg)
        self.sender_client = sender_client
        self.event_logger = event_logger
        self.metric_sender = metric_sender
        self.validator = validator
        self.workflow_id = workflow_id
        self.sending_app = sending_app
        self.flow_name: str | None = flow_name
        self.standard_version: str | None = standard_version

    def reply(self) -> str:
        try:
            self.event_logger.log_message_received(self.incoming_message)
            self.metric_sender.send_message_received_metric()

            msg = parse_message(self.incoming_message, find_groups=False)
            message_control_id = msg.msh.msh_10.value
            message_type = msg.msh.msh_9.to_er7()
            logger.info("Received message type: %s, Control ID: %s", message_type, message_control_id)

            self.validator.validate(msg)
            self.event_logger.log_validation_result(
                self.incoming_message, f"Valid HL7 message - Type: {message_type}", is_success=True
            )

            # Optimized: pass pre-parsed message to avoid redundant parsing
            if self.flow_name and self.flow_name != "mpi":
                try:
                    validate_parsed_message_with_flow_schema(msg, self.incoming_message, self.flow_name)
                    self.event_logger.log_validation_result(
                        self.incoming_message,
                        f"XML validation passed for flow '{self.flow_name}'",
                        is_success=True,
                    )
                except XmlValidationError as e:
                    error_msg = f"XML validation failed for flow '{self.flow_name}': {e}"
                    logger.error(error_msg)
                    self.event_logger.log_validation_result(self.incoming_message, error_msg, is_success=False)
                    self.event_logger.log_message_failed(
                        self.incoming_message, error_msg, "XML schema validation failed"
                    )
                    raise

            if self.standard_version:
                try:
                    validate_parsed_message_with_standard(msg, self.standard_version)
                    self.event_logger.log_validation_result(
                        self.incoming_message,
                        f"Standard HL7 v{self.standard_version} validation passed",
                        is_success=True,
                    )
                except XmlValidationError as e:
                    error_msg = f"Standard validation error: {e}"
                    logger.error(error_msg)
                    self.event_logger.log_validation_result(self.incoming_message, error_msg, is_success=False)
                    self.event_logger.log_message_failed(
                        self.incoming_message, error_msg, "Standard HL7 validation failed"
                    )
                    raise

            try:
                message_sending_app = msg.msh.msh_3.value if msg.msh.msh_3.value else None
            except (AttributeError, IndexError):
                message_sending_app = None
            custom_properties_builder = FLOW_PROPERTY_BUILDERS.get(self.flow_name or "")
            if custom_properties_builder:
                custom_properties = custom_properties_builder(msg, self.workflow_id, message_sending_app)
            else:
                custom_properties = build_common_properties(self.workflow_id, message_sending_app)

            self._send_to_service_bus(message_control_id, custom_properties)

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

    def _send_to_service_bus(self, message_control_id: str, custom_properties: dict[str, str]) -> None:
        try:
            self.sender_client.send_text_message(self.incoming_message, custom_properties)
            logger.info("Message %s sent to Service Bus queue successfully", message_control_id)
            event_id, workflow_id, source_system, received_at = get_metadata_log_values(custom_properties)
            logger.info(
                "Message metadata attached - EventId: %s, WorkflowID: %s, SourceSystem: %s, MessageReceivedAt: %s",
                event_id,
                workflow_id,
                source_system,
                received_at,
            )
        except Exception as e:
            logger.error("Failed to send message %s to Service Bus: %s", message_control_id, str(e))
            raise
