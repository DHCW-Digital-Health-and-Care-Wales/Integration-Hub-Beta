import logging
from typing import Callable

from azure.servicebus import ServiceBusMessage
from event_logger_lib import EventLogger
from hl7apy.core import Message
from hl7apy.parser import parse_message
from message_bus_lib.message_sender_client import MessageSenderClient

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
    logger.debug("Received message")

    incoming_props = {}
    if message.application_properties:
        incoming_props = {}
        for k, v in message.application_properties.items():
            key = k.decode("utf-8") if isinstance(k, bytes) else str(k)
            value = v.decode("utf-8") if isinstance(v, bytes) else str(v)
            incoming_props[key] = value
        logger.info("application_properties keys found: %s", list(incoming_props.keys()) if incoming_props else "none")
        if incoming_props:
            logger.info(
                "Received message with metadata - EventId: %s, WorkflowID: %s, SourceSystem: %s, MessageReceivedAt: %s",
                incoming_props.get("EventId", "N/A"),
                incoming_props.get("WorkflowID", "N/A"),
                incoming_props.get("SourceSystem", "N/A"),
                incoming_props.get("MessageReceivedAt", "N/A"),
            )
        else:
            logger.warning("application_properties exists but is empty after processing")
    else:
        logger.warning("No application_properties found on message")

    try:
        event_logger.log_message_received(message_body, received_audit_text)

        hl7_msg = parse_message(message_body)
        msh_segment = hl7_msg.msh
        logger.debug(f"Message ID: {msh_segment.msh_10.value}")

        transformed_hl7_message = transform(hl7_msg)

        sender_client.send_message(transformed_hl7_message.to_er7(), custom_properties=incoming_props if incoming_props else None)
        if incoming_props:
            logger.info(
                "Forwarded message metadata - EventId: %s, WorkflowID: %s, SourceSystem: %s",
                incoming_props.get("EventId", "N/A"),
                incoming_props.get("WorkflowID", "N/A"),
                incoming_props.get("SourceSystem", "N/A"),
            )

        event_logger.log_message_processed(
            message_body,
            processed_audit_text_builder(hl7_msg),
        )

        return True

    except ValueError as e:
        error_msg = f"Failed to transform {transformer_display_name} message: {e}"
        logger.error(error_msg)

        event_logger.log_message_failed(message_body, error_msg, failed_audit_text)

        return False

    except Exception as e:
        error_msg = f"Unexpected error during message processing: {e}"
        logger.error(error_msg)

        event_logger.log_message_failed(message_body, error_msg, "Unexpected processing error")

        return False


