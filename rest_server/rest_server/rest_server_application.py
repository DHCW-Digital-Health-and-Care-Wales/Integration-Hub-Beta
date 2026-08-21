"""Wires environment configuration to Service Bus/health-check resources and the FastAPI app.

The ASGI app itself (routes, OpenAPI docs, request-size guarding) lives in ``asgi_app.py`` and is
built independently of this wiring so it can be unit tested with a mocked processor.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from event_logger_lib.event_logger import EventLogger
from fastapi import FastAPI
from health_check_lib.health_check_server import TCPHealthCheckServer
from message_bus_lib.connection_config import ConnectionConfig
from message_bus_lib.message_sender_client import MessageSenderClient
from message_bus_lib.message_store_client import MessageStoreClient
from message_bus_lib.servicebus_client_factory import ServiceBusClientFactory
from metric_sender_lib.metric_sender import MetricSender

from .app_config import AppConfig
from .asgi_app import build_fastapi_app
from .content_adapters.base import ContentAdapter
from .content_adapters.soap_adapter import SoapContentAdapter
from .content_adapters.xml_raw_adapter import XmlRawContentAdapter
from .message_processor import RestMessageProcessor
from .validators.base import Validator
from .validators.hl7_xsd_validator import Hl7XsdValidator
from .validators.no_op_validator import NoOpValidator
from .validators.xsd_validator import XsdValidator

log_level_str = os.environ.get("LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, log_level_str, logging.INFO)
logging.basicConfig(level=log_level, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

azure_log_level_str = os.environ.get("AZURE_LOG_LEVEL", "WARN").upper()
azure_log_level = getattr(logging, azure_log_level_str, logging.WARN)
logging.getLogger("azure").setLevel(azure_log_level)


def build_content_adapter(app_config: AppConfig) -> ContentAdapter:
    if app_config.content_adapter == "soap":
        return SoapContentAdapter()
    if app_config.content_adapter == "xml-raw":
        return XmlRawContentAdapter(
            source_identifier_path=app_config.source_identifier_locator,
            message_control_id_path=app_config.message_control_id_locator,
        )
    raise RuntimeError(f"Unsupported content adapter '{app_config.content_adapter}'")


def build_validator(app_config: AppConfig) -> Validator:
    if app_config.validator_type == "hl7-xsd":
        return Hl7XsdValidator(
            schema_group=app_config.validation_schema or "",
            allowed_structures=set(app_config.allowed_hl7_structures),
        )
    if app_config.validator_type == "xsd":
        return XsdValidator(schema_path=app_config.validation_schema or "")
    if app_config.validator_type == "none":
        return NoOpValidator()
    raise RuntimeError(f"Unsupported validator type '{app_config.validator_type}'")


class RestServerApplication:
    """Reads env config, wires Service Bus/health-check resources, and builds the FastAPI app.

    Process lifecycle (startup/shutdown signals) is owned by uvicorn - this class only starts
    and stops its own resources via the FastAPI lifespan context manager.
    """

    def __init__(self) -> None:
        self.sender_client: MessageSenderClient | None = None
        self.message_store_client: MessageStoreClient | None = None
        self.event_logger: EventLogger | None = None
        self.metric_sender: MetricSender | None = None
        self.health_check_server: TCPHealthCheckServer | None = None

    def build_app(self) -> FastAPI:
        app_config = AppConfig.read_env_config()

        client_config = ConnectionConfig(app_config.connection_string, app_config.service_bus_namespace)
        factory = ServiceBusClientFactory(client_config)

        if app_config.egress_topic_name:
            self.sender_client = factory.create_topic_sender_client(
                app_config.egress_topic_name, app_config.egress_session_id
            )
            logger.info("Configured to send messages to topic: %s", app_config.egress_topic_name)
        elif app_config.egress_queue_name:
            self.sender_client = factory.create_queue_sender_client(
                app_config.egress_queue_name, app_config.egress_session_id
            )
            logger.info("Configured to send messages to queue: %s", app_config.egress_queue_name)

        self.message_store_client = factory.create_message_store_client(
            app_config.message_store_queue_name, app_config.microservice_id, app_config.peer_service
        )

        self.event_logger = EventLogger(app_config.workflow_id, app_config.microservice_id)
        self.metric_sender = MetricSender(
            app_config.workflow_id,
            app_config.microservice_id,
            app_config.health_board,
            app_config.peer_service,
        )
        self.health_check_server = TCPHealthCheckServer(app_config.health_check_hostname, app_config.health_check_port)

        processor = RestMessageProcessor(
            content_adapter=build_content_adapter(app_config),
            validator=build_validator(app_config),
            sender_client=self.sender_client,
            event_logger=self.event_logger,
            metric_sender=self.metric_sender,
            message_store_client=self.message_store_client,
            workflow_id=app_config.workflow_id,
            egress_session_id=app_config.egress_session_id,
            allowed_source_identifiers=app_config.allowed_source_identifiers,
            output_format=app_config.output_format,
        )

        @asynccontextmanager
        async def lifespan(_: FastAPI) -> AsyncIterator[None]:
            self._start_resources(app_config)
            yield
            self._stop_resources()

        return build_fastapi_app(
            processor=processor,
            endpoint_path=app_config.endpoint_path,
            max_request_size_bytes=app_config.max_request_size_bytes,
            content_adapter_name=app_config.content_adapter,
            validator_type=app_config.validator_type,
            output_format=app_config.output_format,
            lifespan=lifespan,
        )

    def _start_resources(self, app_config: AppConfig) -> None:
        if self.health_check_server:
            self.health_check_server.start()
        logger.info(
            "REST server ready on endpoint %s (adapter=%s, validator=%s, output=%s, "
            "max request size: %s bytes)",
            app_config.endpoint_path,
            app_config.content_adapter,
            app_config.validator_type,
            app_config.output_format,
            app_config.max_request_size_bytes,
        )

    def _stop_resources(self) -> None:
        logger.info("Shutting down REST server resources...")

        if self.sender_client:
            self.sender_client.close()
            logger.info("Service Bus sender client shut down.")

        if self.message_store_client:
            self.message_store_client.close()
            logger.info("Message store client shut down.")

        if self.health_check_server:
            self.health_check_server.stop()
            logger.info("Health check server shut down.")

        logger.info("REST server shutdown complete.")

