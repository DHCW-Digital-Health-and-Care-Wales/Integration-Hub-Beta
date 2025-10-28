import configparser
import logging
import os

from azure.servicebus import ServiceBusMessage
from event_logger_lib import EventLogger
from health_check_lib.health_check_server import TCPHealthCheckServer
from hl7apy.parser import parse_message
from message_bus_lib.connection_config import ConnectionConfig
from message_bus_lib.servicebus_client_factory import ServiceBusClientFactory
from metric_sender_lib.metric_sender import MetricSender
from processor_manager_lib import ProcessorManager

from hl7_sender.ack_processor import get_ack_result
from hl7_sender.app_config import AppConfig
from hl7_sender.hl7_sender_client import HL7SenderClient

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
    metric_sender = MetricSender(app_config.workflow_id, app_config.microservice_id)

    with (
        factory.create_message_receiver_client(app_config.ingress_queue_name, app_config.ingress_session_id
        ) as receiver_client,
        HL7SenderClient(
            app_config.receiver_mllp_hostname, app_config.receiver_mllp_port, app_config.ack_timeout_seconds
        ) as hl7_sender_client,
        TCPHealthCheckServer(app_config.health_check_hostname, app_config.health_check_port) as health_check_server,
    ):
        logger.info("Processor started.")
        health_check_server.start()

        while processor_manager.is_running:
            receiver_client.receive_messages(
                MAX_BATCH_SIZE,
                lambda message: _process_message(message, hl7_sender_client, event_logger, metric_sender),
            )


def _process_message(
    message: ServiceBusMessage,
    hl7_sender_client: HL7SenderClient,
    event_logger: EventLogger,
    metric_sender: MetricSender,
) -> bool:
    message_body = b"".join(message.body).decode("utf-8")
    logger.info("Received message")

    try:
        event_logger.log_message_received(message_body, "Message received for HL7 sending")

        hl7_msg = parse_message(message_body)
        msh_segment = hl7_msg.msh
        message_id = msh_segment.msh_10.value
        logger.info(f"Message ID: {message_id}")

        ack_response = hl7_sender_client.send_message(message_body)

        event_logger.log_message_processed(message_body, f"Message sent successfully, received ACK: {ack_response}")
        logger.info(f"Sent message: {message_id}")

        ack_success = get_ack_result(ack_response)

        if ack_success:
            metric_sender.send_message_sent_metric()

        return ack_success

    except (TimeoutError, ConnectionError) as e:
        error_msg = f"Failed to send message {message_id}: {e}"
        logger.error(error_msg)

        event_logger.log_message_failed(message_body, error_msg, "Message sending failed - connection/timeout error")

        return False

    except Exception as e:
        error_msg = f"Unexpected error while processing message: {e}"
        logger.error(error_msg)

        event_logger.log_message_failed(message_body, error_msg, "Unexpected processing error")

        return False


if __name__ == "__main__":
    main()
