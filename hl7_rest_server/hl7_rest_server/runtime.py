from __future__ import annotations

import logging
from dataclasses import dataclass

from event_logger_lib.event_logger import EventLogger
from message_bus_lib.connection_config import ConnectionConfig
from message_bus_lib.message_sender_client import MessageSenderClient
from message_bus_lib.message_store_client import MessageStoreClient
from message_bus_lib.servicebus_client_factory import ServiceBusClientFactory
from metric_sender_lib.metric_sender import MetricSender

from hl7_rest_server.app_config import AppConfig
from hl7_rest_server.hl7_ack_builder import HL7AckBuilder
from hl7_rest_server.hl7_message_processor import Hl7MessageProcessor
from hl7_rest_server.hl7_validator import HL7Validator

logger = logging.getLogger(__name__)


@dataclass
class RuntimeContext:
    """Holds the wired-up runtime dependencies shared across requests."""

    config: AppConfig
    processor: Hl7MessageProcessor
    ack_builder: HL7AckBuilder
    sender_client: MessageSenderClient | None = None
    message_store_client: MessageStoreClient | None = None

    def close(self) -> None:
        if self.sender_client:
            try:
                self.sender_client.close()
                logger.info("Service Bus sender client shut down.")
            except Exception as e:
                logger.warning("Error closing Service Bus sender client: %s", e)
        if self.message_store_client:
            try:
                self.message_store_client.close()
                logger.info("Message store client shut down.")
            except Exception as e:
                logger.warning("Error closing message store client: %s", e)


def build_runtime_context(config: AppConfig) -> RuntimeContext:
    """Wire the Service Bus clients, validator and processor from configuration."""
    client_config = ConnectionConfig(config.connection_string, config.service_bus_namespace)
    factory = ServiceBusClientFactory(client_config)

    if config.egress_topic_name:
        sender_client = factory.create_topic_sender_client(config.egress_topic_name, config.egress_session_id)
        logger.info("Configured to send messages to topic: %s", config.egress_topic_name)
    else:
        sender_client = factory.create_queue_sender_client(config.egress_queue_name, config.egress_session_id)
        logger.info("Configured to send messages to queue: %s", config.egress_queue_name)

    message_store_client = factory.create_message_store_client(
        config.message_store_queue_name, config.microservice_id, config.peer_service
    )

    event_logger = EventLogger(config.workflow_id, config.microservice_id)
    metric_sender = MetricSender(
        config.workflow_id, config.microservice_id, config.health_board, config.peer_service
    )
    validator = HL7Validator(config.hl7_version, config.sending_app, config.hl7_validation_flow)
    ack_builder = HL7AckBuilder()

    processor = Hl7MessageProcessor(
        sender_client=sender_client,
        event_logger=event_logger,
        metric_sender=metric_sender,
        validator=validator,
        message_store_client=message_store_client,
        ack_builder=ack_builder,
        workflow_id=config.workflow_id,
        egress_session_id=config.egress_session_id,
        flow_name=config.hl7_validation_flow,
        standard_version=config.hl7_validation_standard,
    )

    return RuntimeContext(
        config=config,
        processor=processor,
        ack_builder=ack_builder,
        sender_client=sender_client,
        message_store_client=message_store_client,
    )
