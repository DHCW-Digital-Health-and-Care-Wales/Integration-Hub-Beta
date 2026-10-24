import logging
import os

from azure.servicebus import ServiceBusMessage
from event_logger_lib import EventLogger
from health_check_lib.health_check_server import TCPHealthCheckServer
from message_bus_lib.connection_config import ConnectionConfig
from message_bus_lib.servicebus_client_factory import ServiceBusClientFactory
from processor_manager_lib import ProcessorManager
from transformer_base_lib.app_config import TransformerConfig, validate_ingress_config

from .app_config import MappingTypeConfig
from .message_processor import LimsWrrsMessageProcessor

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "ERROR").upper())
azure_log_level_str = os.environ.get("AZURE_LOG_LEVEL", "WARN").upper()
azure_log_level = getattr(logging, azure_log_level_str, logging.WARN)
logging.getLogger("azure").setLevel(azure_log_level)
logger = logging.getLogger(__name__)

SERVICE_NAME = "LimsWrrsTransformer"


def main() -> None:
    # Not run_transformer_app: that is strictly one message in / one message out, whereas this
    # service fans one inbound message out to N classified messages.
    config = TransformerConfig.from_env_and_config_file(os.path.join(os.path.dirname(__file__), "config.ini"))
    validate_ingress_config(config.ingress_queue_name, config.ingress_topic_name, config.ingress_subscription_name)
    if not config.egress_topic_name:
        raise RuntimeError("EGRESS_TOPIC_NAME is required: classified messages are published to a topic.")
    if not (config.ingress_topic_name and config.ingress_subscription_name):
        raise RuntimeError("INGRESS_TOPIC_NAME and INGRESS_SUBSCRIPTION_NAME are required for this service.")

    mapping_types = MappingTypeConfig.read_env_config()
    processor_manager = ProcessorManager()
    factory = ServiceBusClientFactory(ConnectionConfig(config.connection_string, config.service_bus_namespace))
    event_logger = EventLogger(config.workflow_id, config.microservice_id)
    ingress_name = f"{config.ingress_topic_name}/{config.ingress_subscription_name}"

    with (
        factory.create_topic_sender_client(config.egress_topic_name, config.egress_session_id) as sender_client,
        factory.create_subscription_receiver_client(
            config.ingress_topic_name, config.ingress_subscription_name, config.ingress_session_id
        ) as receiver_client,
        TCPHealthCheckServer(config.health_check_hostname, config.health_check_port) as health_check_server,
    ):
        logger.info(
            "%s initialised: ingress=%s, egress topic=%s, mapping types=%s",
            SERVICE_NAME,
            ingress_name,
            config.egress_topic_name,
            mapping_types,
        )
        health_check_server.start()

        processor = LimsWrrsMessageProcessor(sender_client, event_logger, mapping_types)

        def handler(message: ServiceBusMessage) -> bool:
            return processor.process(message)

        wrapped_handler = processor_manager.wrap_handler(handler, SERVICE_NAME, ingress_name)
        while processor_manager.is_running:
            receiver_client.receive_messages(config.MAX_BATCH_SIZE, wrapped_handler)


if __name__ == "__main__":
    main()
