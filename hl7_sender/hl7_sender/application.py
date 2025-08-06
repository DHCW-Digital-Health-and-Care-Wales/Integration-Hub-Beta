import configparser
import logging
import os

from azure.servicebus import ServiceBusMessage
from health_check_lib.health_check_server import TCPHealthCheckServer
from hl7apy.parser import parse_message
from message_bus_lib.audit_service_client import AuditServiceClient
from message_bus_lib.connection_config import ConnectionConfig
from message_bus_lib.processing_result import ProcessingResult
from message_bus_lib.servicebus_client_factory import ServiceBusClientFactory

from hl7_sender.ack_processor import get_ack_result
from hl7_sender.app_config import AppConfig
from hl7_sender.hl7_sender_client import HL7SenderClient
from hl7_sender.processor_manager import ProcessorManager

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "ERROR").upper())
logger = logging.getLogger(__name__)

config = configparser.ConfigParser()
config_path = os.path.join(os.path.dirname(__file__), "config.ini")
config.read(config_path)

MAX_BATCH_SIZE = config.getint("DEFAULT", "max_batch_size")


def main() -> None:
    processor_manager = ProcessorManager()

    app_config = AppConfig.read_env_config()
    client_config = ConnectionConfig(app_config.connection_string, app_config.service_bus_namespace)
    factory = ServiceBusClientFactory(client_config)

    with (
        factory.create_message_receiver_client(app_config.ingress_queue_name) as receiver_client,
        HL7SenderClient(
            app_config.receiver_mllp_hostname, app_config.receiver_mllp_port, app_config.ack_timeout_seconds
        ) as hl7_sender_client,
        TCPHealthCheckServer(app_config.health_check_hostname, app_config.health_check_port) as health_check_server,
        factory.create_queue_sender_client(app_config.audit_queue_name) as audit_sender_client,
        AuditServiceClient(audit_sender_client, app_config.workflow_id, app_config.microservice_id) as audit_client,
    ):
        logger.info("Processor started.")
        health_check_server.start()

        while processor_manager.is_running:
            receiver_client.receive_messages(
                MAX_BATCH_SIZE, lambda message: _process_message(message, hl7_sender_client, audit_client)
            )


def _process_message(
    message: ServiceBusMessage, hl7_sender_client: HL7SenderClient, audit_client: AuditServiceClient
) -> ProcessingResult:
    message_body = b"".join(message.body).decode("utf-8")
    logger.info("Received message")

    try:
        audit_client.log_message_received(message_body, "Message received for HL7 sending")

        hl7_msg = parse_message(message_body)
        msh_segment = hl7_msg.msh
        message_id = msh_segment.msh_10.value
        logger.info(f"Message ID: {message_id}")

        ack_response = hl7_sender_client.send_message(message_body)

        audit_client.log_message_processed(message_body, f"Message sent successfully, received ACK: {ack_response}")
        logger.info(f"Sent message: {message_id}")

        return get_ack_result(ack_response)

    except (TimeoutError, ConnectionError) as e:
        error_msg = f"Failed to send message {message_id}: {e}"
        logger.error(error_msg)

        audit_client.log_message_failed(message_body, error_msg, "Message sending failed - connection/timeout error")

        return ProcessingResult.failed(error_msg, retry=True)

    except Exception as e:
        error_msg = f"Unexpected error while processing message: {e}"
        logger.error(error_msg)

        audit_client.log_message_failed(message_body, error_msg, "Unexpected processing error")

        return ProcessingResult.failed(error_msg, retry=True)


if __name__ == "__main__":
    main()
