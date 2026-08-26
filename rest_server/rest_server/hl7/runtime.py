"""Wires the ``hl7`` pipeline's processor from shared infra resources + config."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from message_bus_lib.message_sender_client import MessageSenderClient

from rest_server.app_config import AppConfig
from rest_server.hl7.hl7_ack_builder import HL7AckBuilder
from rest_server.hl7.hl7_message_processor import Hl7MessageProcessor
from rest_server.hl7.hl7_validator import HL7Validator
from rest_server.hl7.risp_routing import MPI_TRANSFORMER_DESTINATION, WRRS_DESTINATION, RispFlowRouter
from rest_server.infra import SharedResources, build_extra_sender_client

logger = logging.getLogger(__name__)


@dataclass
class Hl7RuntimeContext:
    """State attached to ``request.app.state.context`` for the ``hl7`` pipeline's routes."""

    config: AppConfig
    processor: Hl7MessageProcessor
    ack_builder: HL7AckBuilder


def build_hl7_runtime(
    config: AppConfig, resources: SharedResources
) -> tuple[Hl7RuntimeContext, MessageSenderClient | None]:
    """Build the ``hl7`` pipeline's processor (and, for 'risp', its extra WRRS sender client)."""
    validator = HL7Validator(config.hl7_version, config.sending_app, config.hl7_validation_flow)
    ack_builder = HL7AckBuilder()

    risp_router = None
    destination_senders = None
    destination_workflow_ids = None
    wrrs_sender_client = None

    if config.hl7_validation_flow == "risp":
        wrrs_sender_client = build_extra_sender_client(
            resources.factory,
            queue_name=config.wrrs_queue_name,
            topic_name=config.wrrs_topic_name,
            session_id=config.wrrs_egress_session_id or "",
        )
        logger.info("Configured RISP WRRS destination -> %s", config.wrrs_topic_name or config.wrrs_queue_name)

        risp_router = RispFlowRouter()
        destination_senders = {
            MPI_TRANSFORMER_DESTINATION: resources.sender_client,
            WRRS_DESTINATION: wrrs_sender_client,
        }
        destination_workflow_ids = {
            MPI_TRANSFORMER_DESTINATION: config.workflow_id,
            WRRS_DESTINATION: config.wrrs_workflow_id or config.workflow_id,
        }

    processor = Hl7MessageProcessor(
        sender_client=resources.sender_client,
        event_logger=resources.event_logger,
        metric_sender=resources.metric_sender,
        validator=validator,
        message_store_client=resources.message_store_client,
        ack_builder=ack_builder,
        workflow_id=config.workflow_id,
        egress_session_id=config.egress_session_id,
        flow_name=config.hl7_validation_flow,
        standard_version=config.hl7_validation_standard,
        risp_router=risp_router,
        destination_senders=destination_senders,
        destination_workflow_ids=destination_workflow_ids,
    )

    return Hl7RuntimeContext(config=config, processor=processor, ack_builder=ack_builder), wrrs_sender_client
