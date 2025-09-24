import configparser
import logging
import os
from typing import Callable

from event_logger_lib import EventLogger
from health_check_lib.health_check_server import TCPHealthCheckServer
from hl7apy.core import Message
from message_bus_lib.connection_config import ConnectionConfig
from message_bus_lib.servicebus_client_factory import ServiceBusClientFactory
from processor_manager_lib import ProcessorManager

from .app_config import AppConfig

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "ERROR").upper())
logger = logging.getLogger(__name__)


def run_transformer_app(
    transformer_display_name: str,
    transform: Callable[[Message], Message],
    process_message_fn: Callable,
    config_path: str,
) -> None:
    processor_manager = ProcessorManager()

    app_config = AppConfig.read_env_config()
    client_config = ConnectionConfig(app_config.connection_string, app_config.service_bus_namespace)
    factory = ServiceBusClientFactory(client_config)

    event_logger = EventLogger(app_config.workflow_id, app_config.microservice_id)

    config = configparser.ConfigParser()
    config.read(config_path)
    max_batch_size = config.getint("DEFAULT", "max_batch_size")

    with (
        factory.create_queue_sender_client(app_config.egress_queue_name) as sender_client,
        factory.create_message_receiver_client(app_config.ingress_queue_name) as receiver_client,
        TCPHealthCheckServer(app_config.health_check_hostname, app_config.health_check_port) as health_check_server,
    ):
        logger.info(f"{transformer_display_name} Transformer processor started.")
        health_check_server.start()

        while processor_manager.is_running:
            receiver_client.receive_messages(
                max_batch_size,
                lambda message: process_message_fn(message, sender_client, event_logger, transform),
            )


