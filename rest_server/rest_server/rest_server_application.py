"""Reads env config and dispatches to the ``generic`` or ``hl7`` pipeline's FastAPI app.

The ASGI apps themselves (routes, OpenAPI docs, request-size guarding) live in ``asgi_app.py``
(generic) and ``hl7/app.py`` (hl7) and are built independently of this wiring so they can be unit
tested with mocked processors. Resource wiring shared by both pipelines lives in ``infra.py``.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from message_bus_lib.message_sender_client import MessageSenderClient

from .app_config import AppConfig
from .asgi_app import build_fastapi_app
from .content_adapters.base import ContentAdapter
from .content_adapters.soap_adapter import SoapContentAdapter
from .content_adapters.xml_raw_adapter import XmlRawContentAdapter
from .hl7.app import create_hl7_app
from .hl7.runtime import build_hl7_runtime
from .infra import SharedResources, build_shared_resources
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
        self.resources: SharedResources | None = None
        self.extra_sender_client: MessageSenderClient | None = None

    def build_app(self) -> FastAPI:
        app_config = AppConfig.read_env_config()
        if app_config.pipeline == "hl7":
            return self._build_hl7_app(app_config)
        return self._build_generic_app(app_config)

    def _build_generic_app(self, app_config: AppConfig) -> FastAPI:
        self.resources = self._build_shared_resources(app_config)

        processor = RestMessageProcessor(
            content_adapter=build_content_adapter(app_config),
            validator=build_validator(app_config),
            sender_client=self.resources.sender_client,
            event_logger=self.resources.event_logger,
            metric_sender=self.resources.metric_sender,
            message_store_client=self.resources.message_store_client,
            workflow_id=app_config.workflow_id,
            egress_session_id=app_config.egress_session_id,
            allowed_source_identifiers=app_config.allowed_source_identifiers,
            output_format=app_config.output_format or "",
        )

        @asynccontextmanager
        async def lifespan(_: FastAPI) -> AsyncIterator[None]:
            self._start_resources()
            logger.info(
                "REST server ready on endpoint %s (adapter=%s, validator=%s, output=%s, "
                "max request size: %s bytes)",
                app_config.endpoint_path,
                app_config.content_adapter,
                app_config.validator_type,
                app_config.output_format,
                app_config.max_request_size_bytes,
            )
            yield
            self._stop_resources()

        return build_fastapi_app(
            processor=processor,
            endpoint_path=app_config.endpoint_path,
            max_request_size_bytes=app_config.max_request_size_bytes,
            content_adapter_name=app_config.content_adapter or "",
            validator_type=app_config.validator_type or "",
            output_format=app_config.output_format or "",
            lifespan=lifespan,
        )

    def _build_hl7_app(self, app_config: AppConfig) -> FastAPI:
        self.resources = self._build_shared_resources(app_config)
        context, self.extra_sender_client = build_hl7_runtime(app_config, self.resources)

        @asynccontextmanager
        async def lifespan(_: FastAPI) -> AsyncIterator[None]:
            self._start_resources()
            logger.info(
                "HL7 REST pipeline ready (flow=%s, max request size: %s bytes)",
                app_config.hl7_validation_flow or "none",
                app_config.max_request_size_bytes,
            )
            yield
            self._stop_resources()

        return create_hl7_app(context, lifespan=lifespan)

    def _build_shared_resources(self, app_config: AppConfig) -> SharedResources:
        return build_shared_resources(
            connection_string=app_config.connection_string,
            service_bus_namespace=app_config.service_bus_namespace,
            egress_queue_name=app_config.egress_queue_name,
            egress_topic_name=app_config.egress_topic_name,
            egress_session_id=app_config.egress_session_id,
            message_store_queue_name=app_config.message_store_queue_name,
            microservice_id=app_config.microservice_id,
            peer_service=app_config.peer_service,
            workflow_id=app_config.workflow_id,
            health_board=app_config.health_board,
            health_check_hostname=app_config.health_check_hostname,
            health_check_port=app_config.health_check_port,
        )

    def _start_resources(self) -> None:
        assert self.resources is not None  # nosec B101 - always set by build_app before lifespan runs
        self.resources.start()

    def _stop_resources(self) -> None:
        logger.info("Shutting down REST server resources...")
        if self.resources:
            self.resources.stop()
        if self.extra_sender_client:
            try:
                self.extra_sender_client.close()
                logger.info("Extra sender client shut down.")
            except Exception as exc:
                logger.warning("Error closing extra sender client: %s", exc)
        logger.info("REST server shutdown complete.")

