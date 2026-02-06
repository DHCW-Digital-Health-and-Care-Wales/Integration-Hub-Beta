import logging
from typing import Callable

from azure.servicebus import ServiceBusMessage
from event_logger_lib import EventLogger
from hl7apy.core import Message
from hl7apy.parser import parse_message
from message_bus_lib.message_sender_client import MessageSenderClient
from message_bus_lib.metadata_utils import extract_metadata, event_id_for_logger, get_metadata_log_values

logger = logging.getLogger(__name__)


def process_message(
    message: ServiceBusMessage,
    sender_client: MessageSenderClient,
    event_logger: EventLogger,
    transform: Callable[[Message], Message],
    transformer_display_name: str,
    received_audit_text: str,
    processed_audit_text_builder: Callable[[Message], str],
    failed_audit_text: str,
) -> bool:
    message_body = b"".join(message.body).decode("utf-8")
    incoming_props: dict[str, str] | None = extract_metadata(message)
    meta = get_metadata_log_values(incoming_props)
    if incoming_props:
        logger.info(
            "Received message with metadata - EventId: %s, WorkflowID: %s, SourceSystem: %s, MessageReceivedAt: %s",
            meta["event_id"],
            meta["workflow_id"],
            meta["source_system"],
            meta["message_received_at"],
        )
    else:
        logger.warning("No application_properties found on message")

    event_id_opt = event_id_for_logger(meta)
    try:
        event_logger.log_message_received(message_body, received_audit_text, event_id=event_id_opt)

        hl7_msg = parse_message(message_body)
        msh_segment = hl7_msg.msh
        logger.debug(f"Message ID: {msh_segment.msh_10.value}")

        transformed_hl7_message = transform(hl7_msg)

        sender_client.send_message(transformed_hl7_message.to_er7(), custom_properties=incoming_props)

        event_logger.log_message_processed(
            message_body,
            processed_audit_text_builder(hl7_msg),
            event_id=event_id_opt,
        )

        return True

    except ValueError as e:
        error_msg = f"Failed to transform {transformer_display_name} message: {e}"
        logger.error(error_msg)

        event_logger.log_message_failed(
            message_body, error_msg, failed_audit_text, event_id=event_id_opt
        )

        return False

    except Exception as e:
        error_msg = f"Unexpected error during message processing: {e}"
        logger.error(error_msg)

        event_logger.log_message_failed(
            message_body, error_msg, "Unexpected processing error", event_id=event_id_opt
        )

        return False


