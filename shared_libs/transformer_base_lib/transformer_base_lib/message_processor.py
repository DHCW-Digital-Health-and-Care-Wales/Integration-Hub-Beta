import logging
from typing import Any, Callable, Optional

from azure.servicebus import ServiceBusMessage
from event_logger_lib import EventLogger
from message_bus_lib.message_sender_client import MessageSenderClient
from message_bus_lib.metadata_utils import correlation_id_for_logger, extract_metadata, get_metadata_log_values

from .codecs.base_codec import MessageCodec
from .codecs.hl7_er7_codec import Hl7Er7Codec

logger = logging.getLogger(__name__)


def process_message(
    message: ServiceBusMessage,
    sender_client: MessageSenderClient,
    event_logger: EventLogger,
    transform: Callable[[Any], Any],
    transformer_display_name: str,
    received_audit_text: str,
    processed_audit_text_builder: Callable[[Any], str],
    failed_audit_text: str,
    codec: Optional[MessageCodec] = None,
) -> bool:
    codec = codec or Hl7Er7Codec()
    message_body = b"".join(message.body).decode("utf-8")
    incoming_props: dict[str, str] | None = extract_metadata(message)
    meta = get_metadata_log_values(incoming_props)
    if incoming_props:
        logger.info(
            "Received message with metadata - CorrelationId: %s, WorkflowID: %s, SourceSystem: %s, "
            "MessageReceivedAt: %s",
            meta["correlation_id"],
            meta["workflow_id"],
            meta["source_system"],
            meta["message_received_at"],
        )
    else:
        logger.warning("No application_properties found on message")

    correlation_id_opt = correlation_id_for_logger(meta)
    try:
        event_logger.log_message_received(message_body, received_audit_text, correlation_id=correlation_id_opt)

        parsed_message = codec.parse(message_body)

        transformed_message = transform(parsed_message)

        wire_output = codec.serialise(transformed_message)

        sender_client.send_message(wire_output, custom_properties=incoming_props)

        event_logger.log_message_processed(
            wire_output,
            processed_audit_text_builder(parsed_message),
            correlation_id=correlation_id_opt,
        )

        return True

    except ValueError as e:
        error_msg = f"Failed to transform {transformer_display_name} message: {e}"
        logger.error(error_msg)

        event_logger.log_message_failed(
            message_body, error_msg, failed_audit_text, correlation_id=correlation_id_opt
        )

        return False

    except Exception as e:
        error_msg = f"Unexpected error during message processing: {e}"
        logger.error(error_msg)

        event_logger.log_message_failed(
            message_body, error_msg, "Unexpected processing error", correlation_id=correlation_id_opt
        )

        return False


