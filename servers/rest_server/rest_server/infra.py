"""Service Bus/message-store/event-logger/metric-sender/health-check wiring shared by every pipeline.

Factored out of ``rest_server_application.py`` so the ``generic`` and ``hl7`` pipelines build their
resources identically instead of duplicating client construction/teardown.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from event_logger_lib.event_logger import EventLogger
from health_check_lib.health_check_server import TCPHealthCheckServer
from message_bus_lib.connection_config import ConnectionConfig
from message_bus_lib.message_sender_client import MessageSenderClient
from message_bus_lib.message_store_client import MessageStoreClient
from message_bus_lib.servicebus_client_factory import ServiceBusClientFactory
from metric_sender_lib.metric_sender import MetricSender

logger = logging.getLogger(__name__)


@dataclass
class SharedResources:
    """Resources common to every pipeline: Service Bus clients, logging, metrics, health check."""

    factory: ServiceBusClientFactory
    sender_client: MessageSenderClient
    message_store_client: MessageStoreClient
    event_logger: EventLogger
    metric_sender: MetricSender
    health_check_server: TCPHealthCheckServer

    def start(self) -> None:
        self.health_check_server.start()

    def stop(self) -> None:
        logger.info("Shutting down shared REST server resources...")
        try:
            self.sender_client.close()
            logger.info("Service Bus sender client shut down.")
        except Exception as exc:
            logger.warning("Error closing Service Bus sender client: %s", exc)
        try:
            self.message_store_client.close()
            logger.info("Message store client shut down.")
        except Exception as exc:
            logger.warning("Error closing message store client: %s", exc)
        try:
            self.health_check_server.stop()
            logger.info("Health check server shut down.")
        except Exception as exc:
            logger.warning("Error closing health check server: %s", exc)


def build_shared_resources(
    *,
    connection_string: str | None,
    service_bus_namespace: str | None,
    egress_queue_name: str | None,
    egress_topic_name: str | None,
    egress_session_id: str,
    message_store_queue_name: str,
    microservice_id: str,
    peer_service: str,
    workflow_id: str,
    health_board: str,
    health_check_hostname: str | None,
    health_check_port: int | None,
) -> SharedResources:
    """Wire the Service Bus sender/message-store clients plus logging/metrics/health-check resources."""
    client_config = ConnectionConfig(connection_string, service_bus_namespace)
    factory = ServiceBusClientFactory(client_config)

    if egress_topic_name:
        sender_client = factory.create_topic_sender_client(egress_topic_name, egress_session_id)
        logger.info("Configured to send messages to topic: %s", egress_topic_name)
    else:
        sender_client = factory.create_queue_sender_client(egress_queue_name, egress_session_id)
        logger.info("Configured to send messages to queue: %s", egress_queue_name)

    message_store_client = factory.create_message_store_client(
        message_store_queue_name, microservice_id, peer_service
    )

    return SharedResources(
        factory=factory,
        sender_client=sender_client,
        message_store_client=message_store_client,
        event_logger=EventLogger(workflow_id, microservice_id),
        metric_sender=MetricSender(workflow_id, microservice_id, health_board, peer_service),
        health_check_server=TCPHealthCheckServer(health_check_hostname, health_check_port),
    )


def build_extra_sender_client(
    factory: ServiceBusClientFactory,
    *,
    queue_name: str | None,
    topic_name: str | None,
    session_id: str,
) -> MessageSenderClient:
    """Build an additional sender client for a secondary destination (e.g. RISP's WRRS target)."""
    if topic_name:
        return factory.create_topic_sender_client(topic_name, session_id)
    return factory.create_queue_sender_client(queue_name, session_id)
