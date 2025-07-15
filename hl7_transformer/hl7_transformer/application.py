import logging
import os
import signal
import configparser

from azure.servicebus import ServiceBusMessage
from hl7apy.parser import parse_message
from .app_config import AppConfig
from message_bus_lib.connection_config import ConnectionConfig
from message_bus_lib.message_sender_client import MessageSenderClient
from message_bus_lib.servicebus_client_factory import ServiceBusClientFactory
from message_bus_lib.processing_result import ProcessingResult
from message_bus_lib.audit_service_client import AuditServiceClient
from health_check_lib.health_check_server import TCPHealthCheckServer
from .datetime_transformer import transform_datetime

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "ERROR").upper())
logger = logging.getLogger(__name__)

config = configparser.ConfigParser()
config_path = os.path.join(os.path.dirname(__file__), "config.ini")
config.read(config_path)

MAX_BATCH_SIZE = config.getint("DEFAULT", "max_batch_size")
PROCESSOR_RUNNING = True


def shutdown_handler(signum, frame):
    global PROCESSOR_RUNNING
    logger.info("Shutting down the processor")
    PROCESSOR_RUNNING = False


signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)


def main():
    global PROCESSOR_RUNNING

    app_config = AppConfig.read_env_config()
    client_config = ConnectionConfig(app_config.connection_string, app_config.service_bus_namespace)
    factory = ServiceBusClientFactory(client_config)

    with (
        factory.create_queue_sender_client(app_config.egress_queue_name) as sender_client,
        factory.create_queue_sender_client(app_config.audit_queue_name) as audit_sender_client,
        factory.create_message_receiver_client(app_config.ingress_queue_name) as receiver_client,
        AuditServiceClient(audit_sender_client, app_config.workflow_id, app_config.microservice_id) as audit_client,
        TCPHealthCheckServer(app_config.health_check_hostname, app_config.health_check_port) as health_check_server,
    ):
        logger.info("Processor started.")
        health_check_server.start()

        while PROCESSOR_RUNNING:
            receiver_client.receive_messages(
                MAX_BATCH_SIZE,
                lambda message: _process_message(message, sender_client, audit_client),
            )


def _process_message(
    message: ServiceBusMessage,
    sender_client: MessageSenderClient,
    audit_client: AuditServiceClient,
) -> ProcessingResult:
    message_body = b"".join(message.body).decode("utf-8")
    logger.debug("Received message")

    try:
        audit_client.log_message_received(message_body, "Message received for transformation")

        hl7_msg = parse_message(message_body)
        msh_segment = hl7_msg.msh
        logger.debug(f"Message ID: {msh_segment.msh_10.value}")

        created_datetime = msh_segment.msh_7.value

        transformed_datetime = transform_datetime(created_datetime)
        msh_segment.msh_7.value = transformed_datetime

        updated_message = hl7_msg.to_er7()
        sender_client.send_message(updated_message)

        audit_client.log_message_processed(
            message_body,
            f"DateTime transformed from {created_datetime} to {transformed_datetime}",
        )

        return ProcessingResult.successful()

    except ValueError as e:
        error_msg = f"Failed to transform datetime: {e}"
        logger.error(error_msg)

        audit_client.log_message_failed(message_body, error_msg, "DateTime transformation failed")

        return ProcessingResult.failed(str(e))

    except Exception as e:
        error_msg = f"Unexpected error during message processing: {e}"
        logger.error(error_msg)

        audit_client.log_message_failed(message_body, error_msg, "Unexpected processing error")

        return ProcessingResult.failed(str(e), retry=True)


if __name__ == "__main__":
    main()
