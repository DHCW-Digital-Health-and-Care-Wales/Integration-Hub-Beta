import logging
import os

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

    def __init__(self, msg, sender_client: MessageSenderClient):
        super(GenericHandler, self).__init__(msg)
        self.sender_client = sender_client

    def _get_audit_client(self) -> AuditServiceClient:
        # TODO: Do not setup connection in every request
        connection_string = os.environ.get("SERVICE_BUS_CONNECTION_STRING")
        service_bus_namespace = os.environ.get("SERVICE_BUS_NAMESPACE")
        audit_queue_name = os.environ.get("AUDIT_QUEUE_NAME", "audit-queue")
        workflow_id = os.environ.get("WORKFLOW_ID", "phw-2-npi")
        microservice_id = os.environ.get("MICROSERVICE_ID", "phw_hl7_server")

        client_config = ConnectionConfig(connection_string, service_bus_namespace)
        factory = ServiceBusClientFactory(client_config)

        return factory.create_audit_service_client(audit_queue_name, workflow_id, microservice_id)

    def reply(self) -> str:
        audit_client = self._get_audit_client()

        try:
            audit_client.log_message_received(self.incoming_message, "Message received successfully")

            msg = parse_message(self.incoming_message, find_groups=False)
            message_control_id = msg.msh.msh_10.value
            message_type = msg.msh.msh_9.to_er7()
            logger.info("Received message type: %s, Control ID: %s", message_type, message_control_id)

            audit_client.log_validation_result(
                self.incoming_message,
                f"Valid HL7 message - Type: {message_type}",
                is_success=True
            )

            self._send_to_service_bus(message_control_id)

            ack_message = self.create_ack(message_control_id, msg)

            audit_client.log_message_processed(self.incoming_message, "ACK generated successfully")

            logger.info("ACK generated successfully")
            return ack_message
        except HL7apyException as e:
            error_msg = f"HL7 parsing error: {e}"
            logger.error(error_msg)

            audit_client.log_validation_result(
                self.incoming_message,
                error_msg,
                is_success=False
            )

            audit_client.log_message_failed(self.incoming_message, error_msg)

            raise
        except Exception:
            error_msg = f"Unexpected error while processing message: {e}"
            logger.exception(error_msg)

            audit_client.log_message_failed(self.incoming_message, error_msg)
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
