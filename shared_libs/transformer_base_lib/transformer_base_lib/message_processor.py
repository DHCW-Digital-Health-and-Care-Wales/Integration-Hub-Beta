import logging
from typing import Any, Callable

from azure.servicebus import ServiceBusMessage
from event_logger_lib import EventLogger
from hl7apy.core import Message
from hl7apy.parser import parse_message
from message_bus_lib.message_sender_client import MessageSenderClient
from message_bus_lib.metadata_utils import correlation_id_for_logger, extract_metadata, get_metadata_log_values

logger = logging.getLogger(__name__)


def serialise_hl7_message(transformed_message: Any) -> str:
    """Default egress serialisation: HL7 ER7 (pipe-delimited) text."""
    return transformed_message.to_er7()  # type: ignore[no-any-return]


def process_message(
    message: ServiceBusMessage,
    sender_client: MessageSenderClient,
    event_logger: EventLogger,
    transform: Callable[[Any], Any],
    transformer_display_name: str,
    received_audit_text: str,
    processed_audit_text_builder: Callable[[Any], str],
    failed_audit_text: str,
    egress_properties_builder: Callable[[dict[str, str] | None, Any], dict[str, str] | None] | None = None,
    parse_input: Callable[[str], Any] = parse_message,
    serialise_output: Callable[[Any], str] = serialise_hl7_message,
) -> bool:
    """Receive, transform and forward one Service Bus message.

    parse_input and serialise_output default to HL7 ER7 handling. Non-HL7 transformers (for example the
    WPAS XML to FHIR transformer) override them so their payload is never run through the HL7 parser.
    """
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

        parsed_message = parse_input(message_body)
        # MSH-10 only exists on HL7 messages; other payload types have no equivalent to log
        if isinstance(parsed_message, Message):
            logger.debug(f"Message ID: {parsed_message.msh.msh_10.value}")

        transformed_message = transform(parsed_message)

        egress_props = (
            egress_properties_builder(incoming_props, transformed_message)
            if egress_properties_builder
            else incoming_props
        )
        egress_body = serialise_output(transformed_message)
        sender_client.send_message(egress_body, custom_properties=egress_props)

        event_logger.log_message_processed(
            egress_body,
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


