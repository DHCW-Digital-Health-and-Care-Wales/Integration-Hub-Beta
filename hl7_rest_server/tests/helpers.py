"""Shared test helpers for the hl7_rest_server unit tests."""

from __future__ import annotations

from unittest.mock import MagicMock

from hl7_rest_server.app_config import AppConfig
from hl7_rest_server.hl7_ack_builder import HL7AckBuilder
from hl7_rest_server.hl7_message_processor import Hl7MessageProcessor
from hl7_rest_server.hl7_validator import HL7Validator
from hl7_rest_server.runtime import RuntimeContext

# A minimal, valid ER7 ADT^A28 message (segments separated by CR).
VALID_ER7_MESSAGE = (
    "MSH|^~\\&|252|252|MPI|MPI|20240101120000||ADT^A28^ADT_A05|MSGID12345|P|2.5\r"
    "EVN|A28|20240101120000\r"
    "PID|1||123456^^^NHS||SMITH^JOHN||19800101|M"
)


def make_config(
    *,
    environment: str = "DEV",
    max_message_size_bytes: int = 1048576,
    hl7_version: str | None = None,
    sending_app: str | None = None,
    hl7_validation_flow: str | None = None,
    hl7_validation_standard: str | None = None,
) -> AppConfig:
    return AppConfig(
        connection_string="Endpoint=sb://test;",
        egress_queue_name="egress-queue",
        egress_topic_name=None,
        egress_session_id="session",
        service_bus_namespace=None,
        message_store_queue_name="store-queue",
        workflow_id="test-workflow",
        microservice_id="hl7_rest_server",
        health_board="TEST",
        peer_service="MPI",
        hl7_version=hl7_version,
        sending_app=sending_app,
        environment=environment,
        host="0.0.0.0",  # nosec B104 - test config only
        port=8080,
        hl7_validation_flow=hl7_validation_flow,
        hl7_validation_standard=hl7_validation_standard,
        max_message_size_bytes=max_message_size_bytes,
    )


def build_test_context(
    *,
    config: AppConfig | None = None,
    hl7_version: str | None = None,
    sending_app: str | None = None,
    flow_name: str | None = None,
    standard_version: str | None = None,
) -> tuple[RuntimeContext, MagicMock, MagicMock]:
    """Return a RuntimeContext wired with mocked Service Bus + store clients.

    Returns the context along with the sender and store mocks for assertions.
    """
    config = config or make_config(
        hl7_version=hl7_version,
        sending_app=sending_app,
        hl7_validation_flow=flow_name,
        hl7_validation_standard=standard_version,
    )
    sender_client = MagicMock()
    store_client = MagicMock()
    event_logger = MagicMock()
    metric_sender = MagicMock()
    validator = HL7Validator(hl7_version, sending_app, flow_name)
    ack_builder = HL7AckBuilder()

    processor = Hl7MessageProcessor(
        sender_client=sender_client,
        event_logger=event_logger,
        metric_sender=metric_sender,
        validator=validator,
        message_store_client=store_client,
        ack_builder=ack_builder,
        workflow_id=config.workflow_id,
        egress_session_id=config.egress_session_id,
        flow_name=flow_name,
        standard_version=standard_version,
    )

    context = RuntimeContext(
        config=config,
        processor=processor,
        ack_builder=ack_builder,
        sender_client=sender_client,
        message_store_client=store_client,
    )
    return context, sender_client, store_client
