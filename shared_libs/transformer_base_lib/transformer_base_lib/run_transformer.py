from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from azure.servicebus import ServiceBusMessage
from event_logger_lib import EventLogger
from health_check_lib.health_check_server import TCPHealthCheckServer
from message_bus_lib.connection_config import ConnectionConfig
from message_bus_lib.servicebus_client_factory import ServiceBusClientFactory
from processor_manager_lib import ProcessorManager

from .app_config import TransformerConfig
from .message_processor import process_message

if TYPE_CHECKING:
    from .base_transformer import BaseTransformer

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "ERROR").upper())
logger = logging.getLogger(__name__)


def run_transformer_app(transformer: BaseTransformer) -> None:
    
    from .base_transformer import BaseTransformer
    
    if not isinstance(transformer, BaseTransformer):
        raise TypeError("transformer must be an instance of BaseTransformer")
    
    processor_manager = ProcessorManager()
    config = TransformerConfig.from_env_and_config_file(transformer.config_path)
    
    client_config = ConnectionConfig(config.connection_string, config.service_bus_namespace)
    factory = ServiceBusClientFactory(client_config)
    event_logger = EventLogger(config.workflow_id, config.microservice_id)

    with (
        factory.create_queue_sender_client(config.egress_queue_name, config.egress_session_id) as sender_client,
        factory.create_message_receiver_client(config.ingress_queue_name, config.ingress_session_id) as receiver_client,
        TCPHealthCheckServer(config.health_check_hostname, config.health_check_port) as health_check_server,
    ):
        logger.info(f"{transformer.transformer_name} Transformer processor started.")
        health_check_server.start()

        def message_processor(message: ServiceBusMessage) -> bool:
            return process_message(
                message=message,
                sender_client=sender_client,
                event_logger=event_logger,
                transform=transformer.transform_message,
                transformer_display_name=transformer.transformer_name,
                received_audit_text=transformer.get_received_audit_text(),
                processed_audit_text_builder=transformer.get_processed_audit_text,
                failed_audit_text=f"{transformer.transformer_name} transformation failed",
            )

        while processor_manager.is_running:
            receiver_client.receive_messages(
                config.MAX_BATCH_SIZE,
                message_processor,
            )


