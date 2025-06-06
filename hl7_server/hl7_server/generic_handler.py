import logging
import os

from hl7apy.core import Message
from hl7apy.exceptions import HL7apyException
from hl7apy.mllp import AbstractHandler
from hl7apy.parser import parse_message

from .hl7_ack_builder import HL7AckBuilder
from message_bus_lib.servicebus_client_factory import ServiceBusClientFactory
from message_bus_lib.connection_config import ConnectionConfig

# Configure logging
logger = logging.getLogger(__name__)


class GenericHandler(AbstractHandler):
    def reply(self) -> str:
        connection_string = os.getenv("QUEUE_CONNECTION_STRING")
        namespace = os.getenv("SERVICE_BUS_NAMESPACE")
        
        config = ConnectionConfig(
            connection_string=connection_string or "",
            service_bus_namespace=namespace or ""
        )
        
        self.client_factory = ServiceBusClientFactory(config)
        self.queue_name = os.getenv("QUEUE_NAME", "local-inthub-phw-ingress")

        try:
            msg = parse_message(self.incoming_message, find_groups=False)
            message_control_id = msg.msh.msh_10.value
            message_type = msg.msh.msh_9.to_er7()
            logger.info("Received message type: %s, Control ID: %s", message_type, message_control_id)

            # Send message to Service Bus queue
            self._send_to_service_bus(message_control_id)

            ack_message = self.create_ack(message_control_id, msg)
            logger.info("ACK generated successfully")
            return ack_message
        except HL7apyException as e:
            logger.error("HL7 parsing error: %s", e)
            raise
        except Exception:
            logger.exception("Unexpected error while processing message")
            raise

    def create_ack(self, message_control_id: str, msg: Message) -> str:
        ack_builder = HL7AckBuilder()
        ack_msg = ack_builder.build_ack(message_control_id, msg)
        return ack_msg.to_mllp()
    
    def _send_to_service_bus(self, message_control_id: str) -> bool:
        try:
            with self.client_factory.create_queue_sender_client(self.queue_name) as sender:
                sender.send_text_message(self.incoming_message)
            
            logger.info("Message %s sent to Service Bus queue successfully", message_control_id)
        except Exception as e:
            logger.error("Failed to send message %s to Service Bus: %s", message_control_id, str(e))
            raise
