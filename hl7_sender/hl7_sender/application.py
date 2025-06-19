import logging
import os
import signal
import configparser

from azure.servicebus import ServiceBusMessage
from hl7.client import MLLPClient
from hl7apy.parser import parse_message

from hl7_sender.ack_processor import get_ack_result
from hl7_sender.app_config import AppConfig
from message_bus_lib.connection_config import ConnectionConfig
from message_bus_lib.servicebus_client_factory import ServiceBusClientFactory
from message_bus_lib.processing_result import ProcessingResult

logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'ERROR').upper()
)
logger = logging.getLogger(__name__)

config = configparser.ConfigParser()
config_path = os.path.join(os.path.dirname(__file__), 'config.ini')
config.read(config_path)

MAX_BATCH_SIZE = config.getint('DEFAULT', 'max_batch_size')
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

    with factory.create_message_receiver_client(app_config.ingress_queue_name) as receiver_client, \
          MLLPClient(app_config.receiver_mllp_hostname, app_config.receiver_mllp_port) as mllp_client:
        logger.info("Processor started.")

        while PROCESSOR_RUNNING:
            receiver_client.receive_messages(MAX_BATCH_SIZE,
                                             lambda message: _process_message(message, mllp_client))

def _process_message(message: ServiceBusMessage, mllp_client: MLLPClient) -> ProcessingResult:
    message_body = b''.join(message.body).decode('utf-8')
    logger.info("Received message")

    hl7_msg = parse_message(message_body)
    msh_segment = hl7_msg.msh
    message_id = msh_segment.msh_10.value
    logger.info(f"Message ID: {message_id}")

    ack_response = mllp_client.send_message(message_body).decode('utf-8')

    logger.info(f"Sent message: {message_id}")
    return get_ack_result(ack_response)


if __name__ == "__main__":
    main()
