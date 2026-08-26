"""Shared test helpers for the rest_server ``hl7`` pipeline unit tests."""

from __future__ import annotations

from unittest.mock import MagicMock

from rest_server.app_config import AppConfig
from rest_server.hl7.hl7_ack_builder import HL7AckBuilder
from rest_server.hl7.hl7_message_processor import Hl7MessageProcessor
from rest_server.hl7.hl7_validator import HL7Validator
from rest_server.hl7.risp_routing import MPI_TRANSFORMER_DESTINATION, WRRS_DESTINATION, RispFlowRouter
from rest_server.hl7.runtime import Hl7RuntimeContext

# A minimal, valid ER7 ADT^A28 message (segments separated by CR).
VALID_ER7_MESSAGE = (
    "MSH|^~\\&|252|252|MPI|MPI|20240101120000||ADT^A28^ADT_A05|MSGID12345|P|2.5\r"
    "EVN|A28|20240101120000\r"
    "PID|1||123456^^^NHS||SMITH^JOHN||19800101|M"
)

# RISP sample messages (MSH.3=349, version 2.5.1).
RISP_A28_MESSAGE = (
    "MSH|^~\\&|349|349|MPI|MPI|20240101120000||ADT^A28^ADT_A05|RISPMSG001|P|2.5.1\r"
    "EVN|A28|20240101120000\r"
    "PID|1||654321^^^NHS||DOE^JANE||19900101|F"
)
RISP_A40_MESSAGE = (
    "MSH|^~\\&|349|349|MPI|MPI|20240101120000||ADT^A40^ADT_A39|RISPMSG002|P|2.5.1\r"
    "EVN|A40|20240101120000\r"
    "PID|1||654321^^^NHS||DOE^JANE||19900101|F"
)
RISP_ORU_R01_MESSAGE = (
    "MSH|^~\\&|350|350|MPI|MPI|20240101120000||ORU^R01^ORU_R01|RISPMSG003|P|2.5.1\r"
    "PID|1||654321^^^NHS||DOE^JANE||19900101|F\r"
    "OBR|1||ORDER1||\r"
    "OBX|1|ST|TEST||RESULT"
)


def make_config(
    *,
    environment: str = "DEV",
    max_request_size_bytes: int = 1048576,
    hl7_version: str | None = None,
    sending_app: str | None = None,
    hl7_validation_flow: str | None = None,
    hl7_validation_standard: str | None = None,
    wrrs_queue_name: str | None = None,
    wrrs_egress_session_id: str | None = None,
    wrrs_workflow_id: str | None = None,
) -> AppConfig:
    if hl7_validation_flow == "risp":
        wrrs_queue_name = wrrs_queue_name or "wrrs-queue"
        wrrs_egress_session_id = wrrs_egress_session_id or "risp-to-wrrs"
        wrrs_workflow_id = wrrs_workflow_id or "risp-to-wrrs"

    return AppConfig(
        connection_string="Endpoint=sb://test;",
        egress_queue_name="egress-queue",
        egress_topic_name=None,
        egress_session_id="session",
        service_bus_namespace=None,
        message_store_queue_name="store-queue",
        workflow_id="test-workflow",
        microservice_id="rest-server",
        health_board="TEST",
        peer_service="MPI",
        health_check_hostname=None,
        health_check_port=None,
        host="0.0.0.0",  # nosec B104 - test config only
        port=8080,
        endpoint_path="/ingest",
        content_adapter=None,
        validator_type=None,
        validation_schema=None,
        allowed_hl7_structures=[],
        allowed_source_identifiers=[],
        source_identifier_locator=None,
        message_control_id_locator=None,
        output_format=None,
        pipeline="hl7",
        environment=environment,
        hl7_version=hl7_version,
        sending_app=sending_app,
        hl7_validation_flow=hl7_validation_flow,
        hl7_validation_standard=hl7_validation_standard,
        wrrs_queue_name=wrrs_queue_name,
        wrrs_topic_name=None,
        wrrs_egress_session_id=wrrs_egress_session_id,
        wrrs_workflow_id=wrrs_workflow_id,
        max_request_size_bytes=max_request_size_bytes,
    )


def build_test_context(
    *,
    config: AppConfig | None = None,
    hl7_version: str | None = None,
    sending_app: str | None = None,
    flow_name: str | None = None,
    standard_version: str | None = None,
) -> tuple[Hl7RuntimeContext, MagicMock, MagicMock, MagicMock | None]:
    """Return an ``Hl7RuntimeContext`` wired with mocked Service Bus + store clients.

    Returns the context along with the sender, store and (for the 'risp' flow) WRRS sender mocks.
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
    validator = HL7Validator(config.hl7_version, config.sending_app, config.hl7_validation_flow)
    ack_builder = HL7AckBuilder()

    risp_router = None
    destination_senders = None
    destination_workflow_ids = None
    wrrs_sender_client = None

    if flow_name == "risp":
        risp_router = RispFlowRouter()
        wrrs_sender_client = MagicMock()
        destination_senders = {
            MPI_TRANSFORMER_DESTINATION: sender_client,
            WRRS_DESTINATION: wrrs_sender_client,
        }
        destination_workflow_ids = {
            MPI_TRANSFORMER_DESTINATION: config.workflow_id,
            WRRS_DESTINATION: config.wrrs_workflow_id or "risp-to-wrrs",
        }

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
        risp_router=risp_router,
        destination_senders=destination_senders,
        destination_workflow_ids=destination_workflow_ids,
    )

    context = Hl7RuntimeContext(config=config, processor=processor, ack_builder=ack_builder)
    return context, sender_client, store_client, wrrs_sender_client
