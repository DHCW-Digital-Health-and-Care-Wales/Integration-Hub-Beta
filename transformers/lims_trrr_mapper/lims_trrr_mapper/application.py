"""LIMS -> TRRR identifier mapper.

Consumes LIMS ADT messages from a filtered subscription on the LIMS topic, maps them to the parameters of a
TRRR stored procedure (``TRRR_MAPPING_TYPE`` selects NHS-ID update or merge) and publishes those parameters as
JSON to the TRRR mapped topic. The per-board TRRR database senders subscribe to that topic and only execute
the stored procedure, so the HL7 mapping runs once per message instead of once per health board.
"""

from __future__ import annotations

import json
import logging
import os

from azure.servicebus import ServiceBusReceivedMessage
from event_logger_lib import EventLogger
from health_check_lib.health_check_server import TCPHealthCheckServer
from message_bus_lib.connection_config import ConnectionConfig
from message_bus_lib.dead_letter import DeadLetterMessage
from message_bus_lib.message_sender_client import MessageSenderClient
from message_bus_lib.metadata_utils import correlation_id_for_logger, extract_metadata, get_metadata_log_values
from message_bus_lib.servicebus_client_factory import ServiceBusClientFactory
from processor_manager_lib import ProcessorManager

from lims_trrr_mapper.app_config import AppConfig
from lims_trrr_mapper.identifier_mapper import map_trrr_identifiers
from lims_trrr_mapper.msh_extractor import extract_msh_for_logging

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())
azure_log_level_str = os.environ.get("AZURE_LOG_LEVEL", "WARN").upper()
azure_log_level = getattr(logging, azure_log_level_str, logging.WARN)
logging.getLogger("azure").setLevel(azure_log_level)
logger = logging.getLogger(__name__)

# Application properties added to every published request. MessageControlId and MessageType let the senders log
# the request without the payload. No routing property is needed: every board sender receives every request and
# tells NHS-ID updates and merges apart from the JSON body.
MESSAGE_CONTROL_ID_KEY = "MessageControlId"
MESSAGE_TYPE_KEY = "MessageType"


def build_egress_properties(
    incoming_props: dict[str, str] | None,
    control_id: str,
    message_type: str,
) -> dict[str, str]:
    """Forward the incoming tracking properties and add the TRRR logging properties."""
    props = dict(incoming_props or {})
    props[MESSAGE_CONTROL_ID_KEY] = control_id
    # Keep the upstream MessageType (e.g. "A40") if present; only fill it in when missing.
    props.setdefault(MESSAGE_TYPE_KEY, message_type)
    return props


def process_message(
    message: ServiceBusReceivedMessage,
    sender_client: MessageSenderClient,
    app_config: AppConfig,
    event_logger: EventLogger,
) -> bool:
    message_body = b"".join(message.body).decode("utf-8")
    incoming_props = extract_metadata(message)
    meta = get_metadata_log_values(incoming_props)
    correlation_id_opt = correlation_id_for_logger(meta)
    mapping_type = app_config.mapping_type

    # Extract MSH ONLY for Information Governance compliant logging
    msh_info = extract_msh_for_logging(message_body)

    logger.info(
        "LIMS message received for TRRR %s mapping - CorrelationId: %s, MessageControlId: %s, MessageType: %s",
        mapping_type,
        meta["correlation_id"],
        msh_info.control_id,
        msh_info.message_type,
    )
    event_logger.log_message_received(
        msh_info.msh_text,
        f"Message received for TRRR {mapping_type} mapping",
        correlation_id=correlation_id_opt,
    )

    # A message that cannot be mapped (missing LIMS authority, missing NHS identifier, missing MRG, ...)
    # will never succeed on redelivery, so dead-letter it straight away.
    try:
        request = map_trrr_identifiers(message_body, mapping_type)
    except ValueError as mapping_err:
        event_logger.log_message_failed(
            msh_info.msh_text,
            f"TRRR {mapping_type} mapping failed: {mapping_err}",
            correlation_id=correlation_id_opt,
        )
        logger.error(
            "TRRR %s mapping failed (%s). Dead-lettering. MessageControlId: %s, MessageType: %s",
            mapping_type,
            mapping_err,
            msh_info.control_id,
            msh_info.message_type,
        )
        raise DeadLetterMessage(reason="MappingFailed", description=str(mapping_err)) from mapping_err

    egress_props = build_egress_properties(incoming_props, msh_info.control_id, msh_info.message_type)

    try:
        # Reuse the source MessageId so the published request is traceable to the originating HL7 message.
        sender_client.send_text_message(
            json.dumps(request),
            custom_properties=egress_props,
            message_id=message.message_id,
        )
    except Exception:
        # Publishing is the only side effect, so abandoning and retrying is safe.
        logger.exception(
            "Failed to publish TRRR %s request to %s. Abandoning for retry. MessageControlId: %s",
            mapping_type,
            app_config.egress_topic_name,
            msh_info.control_id,
        )
        return False

    # Post-publish logging is best effort: a logging failure must not cause the request to be published twice.
    try:
        event_logger.log_message_processed(
            msh_info.msh_text,
            f"TRRR {mapping_type} request published to {app_config.egress_topic_name}",
            correlation_id=correlation_id_opt,
        )
    except Exception:
        logger.exception("Failed to log message processed event - request was already published")

    logger.info(
        "TRRR %s request published to %s. MessageControlId: %s",
        mapping_type,
        app_config.egress_topic_name,
        msh_info.control_id,
    )
    return True


def main() -> None:
    processor_manager = ProcessorManager()
    app_config = AppConfig.read_env_config()
    client_config = ConnectionConfig(app_config.connection_string, app_config.service_bus_namespace)
    factory = ServiceBusClientFactory(client_config)
    event_logger = EventLogger(app_config.workflow_id, app_config.microservice_id)

    logger.info(
        "Starting lims_trrr_mapper (%s) %s/%s (session %s) -> %s (session %s)",
        app_config.mapping_type,
        app_config.ingress_topic_name,
        app_config.ingress_subscription_name,
        app_config.ingress_session_id,
        app_config.egress_topic_name,
        app_config.egress_session_id,
    )

    with (
        TCPHealthCheckServer(app_config.health_check_hostname, app_config.health_check_port) as health_check_server,
        factory.create_topic_sender_client(app_config.egress_topic_name, app_config.egress_session_id) as sender,
        factory.create_subscription_receiver_client(
            app_config.ingress_topic_name,
            app_config.ingress_subscription_name,
            app_config.ingress_session_id,
        ) as subscription_receiver_client,
    ):
        health_check_server.start()
        logger.info("Subscription receiver client initialized. Processing messages...")

        while processor_manager.is_running:
            subscription_receiver_client.receive_messages(
                app_config.max_batch_size,
                lambda msg: process_message(msg, sender, app_config, event_logger),
            )


if __name__ == "__main__":
    main()
