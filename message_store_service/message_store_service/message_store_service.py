import logging

from event_logger_lib import EventLogger
from health_check_lib.health_check_server import TCPHealthCheckServer
from message_bus_lib.connection_config import ConnectionConfig
from message_bus_lib.message_receiver_client import MessageReceiverClient
from message_bus_lib.servicebus_client_factory import ServiceBusClientFactory
from processor_manager_lib.processor_manager import ProcessorManager

from .app_config import AppConfig
from .db_client import DatabaseClient
from .message_record_builder import build_message_records

logger = logging.getLogger(__name__)


class MessageStoreService:

    def __init__(self, batch_size: int) -> None:
        self.config = AppConfig.read_env_config()
        self.processor_manager = ProcessorManager()
        self.batch_size = batch_size
        self.db_client = DatabaseClient(
            sql_server=self.config.sql_server,
            sql_database=self.config.sql_database,
            sql_username=self.config.sql_username,
            sql_password=self.config.sql_password,
            sql_encrypt=self.config.sql_encrypt,
            sql_trust_server_certificate=self.config.sql_trust_server_certificate,
            managed_identity_client_id=self.config.managed_identity_client_id,
        )

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
            self.db_client,
        ):
            logger.info("Listening for messages on queue: %s", self.config.ingress_queue_name)
            health_check_server.start()
            self._process_messages(receiver_client, event_logger)

        logger.info("Message Store Service stopped")

    def _process_messages(self, receiver: MessageReceiverClient, event_logger: EventLogger) -> None:
        def process_batch(messages: list) -> bool:
            try:
                records = build_message_records(messages)
                self.db_client.store_messages(records)
                logger.info("Batch of %d message(s) stored successfully", len(records))
                return True
            except Exception as e:
                logger.error("Failed to process batch of %d message(s): %s", len(messages), e)
                event_logger.log_message_failed(
                    "<batch>",
                    f"Batch processing failed: {e}",
                    "Batch insert failed",
                )
                return False

        while self.processor_manager.is_running:
            receiver.receive_messages_batch(
                num_of_messages=self.batch_size, batch_processor=process_batch
            )
