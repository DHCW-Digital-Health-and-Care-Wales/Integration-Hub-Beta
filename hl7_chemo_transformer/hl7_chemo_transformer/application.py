import configparser
import logging
import os

from azure.servicebus import ServiceBusMessage
from event_logger_lib import EventLogger
from health_check_lib.health_check_server import TCPHealthCheckServer
from hl7apy.core import Message
from hl7apy.parser import parse_message
from message_bus_lib.connection_config import ConnectionConfig
from message_bus_lib.message_sender_client import MessageSenderClient
from message_bus_lib.servicebus_client_factory import ServiceBusClientFactory
from processor_manager_lib import ProcessorManager

from .app_config import AppConfig
from .chemocare_transformer import transform_chemocare_message

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
    event_logger = EventLogger(app_config.workflow_id, app_config.microservice_id)

    with (
        factory.create_queue_sender_client(app_config.egress_queue_name) as sender_client,
        factory.create_message_receiver_client(app_config.ingress_queue_name) as receiver_client,
        TCPHealthCheckServer(app_config.health_check_hostname, app_config.health_check_port) as health_check_server,
    ):
        logger.info("Chemocare Transformer processor started.")
        health_check_server.start()

        while processor_manager.is_running:
            receiver_client.receive_messages(
                MAX_BATCH_SIZE,
                lambda message: _process_message(message, sender_client, event_logger),
            )


def _process_message(
    message: ServiceBusMessage,
    sender_client: MessageSenderClient,
    event_logger: EventLogger,
) -> bool:
    message_body = b"".join(message.body).decode("utf-8")
    logger.debug("Received message")

    try:
        event_logger.log_message_received(message_body, "Message received for Chemocare transformation")

        hl7_msg = parse_message(message_body)
        msh_segment = hl7_msg.msh
        logger.debug(f"Message ID: {msh_segment.msh_10.value}")

        sending_app = _get_sending_app(hl7_msg)
        logger.info(f"Applying Chemocare transformation for SENDING_APP: {sending_app}")

        transformed_hl7_message = transform_chemocare_message(hl7_msg)

        sender_client.send_message(transformed_hl7_message.to_er7())

        event_logger.log_message_processed(
            message_body,
            f"Chemocare transformation applied for SENDING_APP: {sending_app}",
        )

        return True

    except ValueError as e:
        error_msg = f"Failed to transform Chemocare message: {e}"
        logger.error(error_msg)

        event_logger.log_message_failed(message_body, error_msg, "Chemocare transformation failed")

        return False

    except Exception as e:
        error_msg = f"Unexpected error during message processing: {e}"
        logger.error(error_msg)

        event_logger.log_message_failed(message_body, error_msg, "Unexpected processing error")

        return False


def _get_sending_app(hl7_msg: Message) -> str:
    try:
        return hl7_msg.msh.msh_3.msh_3_1.value
    except (AttributeError, IndexError):
        return "UNKNOWN"


if __name__ == "__main__":
    main()
