import logging

from event_logger_lib import EventLogger
from health_check_lib.health_check_server import TCPHealthCheckServer
from message_bus_lib.connection_config import ConnectionConfig
from message_bus_lib.message_receiver_client import MessageReceiverClient
from message_bus_lib.servicebus_client_factory import ServiceBusClientFactory
from processor_manager_lib.processor_manager import ProcessorManager

from .app_config import AppConfig
from .message_processor import process_message

logger = logging.getLogger(__name__)


class MessageStoreService:

    def __init__(self, batch_size: int) -> None:
        self.config = AppConfig.read_env_config()
        self.processor_manager = ProcessorManager()
        self.batch_size = batch_size

    def run(self) -> None:
        logger.info("Starting Message Store Service")

        client_config = ConnectionConfig(
            connection_string=self.config.connection_string,
            service_bus_namespace=self.config.service_bus_namespace
        )

        factory = ServiceBusClientFactory(client_config)

        event_logger = EventLogger(
            workflow_id="message_store",
            microservice_id=self.config.microservice_id
        )

        with (
            factory.create_message_receiver_client(
                queue_name=self.config.ingress_queue_name,
                session_id=None
            ) as receiver_client,
            TCPHealthCheckServer(
                self.config.health_check_hostname, self.config.health_check_port
            ) as health_check_server,
        ):
            logger.info(f"Listening for messages on queue: {self.config.ingress_queue_name}")
            health_check_server.start()
            self._process_messages(receiver_client, event_logger)

        logger.info("Message Store Service stopped")

    def _process_messages(self, receiver: MessageReceiverClient, event_logger: EventLogger) -> None:
        while self.processor_manager.is_running:
            receiver.receive_messages(
                num_of_messages=self.batch_size,
                message_processor=lambda message: process_message(message, event_logger)
            )
