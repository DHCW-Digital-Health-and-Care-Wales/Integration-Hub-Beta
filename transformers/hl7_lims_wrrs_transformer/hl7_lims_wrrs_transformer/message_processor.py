"""Classifies each inbound LIMS ADT message and fans it out to one classified message per matching rule."""
from __future__ import annotations

import logging
import uuid

from azure.servicebus import ServiceBusMessage
from event_logger_lib import EventLogger
from hl7apy.core import Message
from hl7apy.parser import parse_message
from message_bus_lib.dead_letter import DeadLetterMessage
from message_bus_lib.message_sender_client import MessageSenderClient
from message_bus_lib.metadata_utils import correlation_id_for_logger, extract_metadata, get_metadata_log_values

from .app_config import MappingTypeConfig
from .classifier import classify_message, get_trigger_event

logger = logging.getLogger(__name__)

# Fixed contracts with the Terraform subscription filters / downstream mapping services.
MAPPING_TYPE_KEY = "MappingType"
PROCESSING_ID_KEY = "ProcessingId"
ORIGINAL_MESSAGE_ID_KEY = "OriginalMessageId"

UNSUPPORTED_MESSAGE_REASON = "Unsupported message type"
INVALID_MESSAGE_REASON = "Invalid HL7 message"


class LimsWrrsMessageProcessor:
    """Handler for ``MessageReceiverClient.receive_messages``.

    Fan-out and partial failure:
    * Each path is sent independently, so a failure on one path does not stop the others.
    * If any path failed, the handler returns False and the inbound message is abandoned for
      redelivery (and eventually dead-lettered by Service Bus after max delivery count).
    * Every path is sent with a deterministic Service Bus ``message_id``
      (``<original message_id>-<MappingType>``). On redelivery, paths that were already sent carry
      the same id, so Service Bus duplicate detection on the classified topic drops them instead of
      republishing. The id is used for de-duplication only: the original MessageId is carried
      unchanged in the ``OriginalMessageId`` application property.
    """

    def __init__(
        self,
        sender_client: MessageSenderClient,
        event_logger: EventLogger,
        mapping_types: MappingTypeConfig,
    ) -> None:
        self._sender_client = sender_client
        self._event_logger = event_logger
        self._mapping_types = mapping_types

    def process(self, message: ServiceBusMessage) -> bool:
        message_body = b"".join(message.body).decode("utf-8")
        incoming_props: dict[str, str] = extract_metadata(message) or {}
        meta = get_metadata_log_values(incoming_props)
        correlation_id = correlation_id_for_logger(meta)

        self._event_logger.log_message_received(
            message_body, "LIMS WRRS message received", correlation_id=correlation_id
        )

        hl7_msg = self._parse_or_dead_letter(message, message_body, correlation_id)
        original_message_id = self._resolve_original_message_id(message, hl7_msg)
        mapping_types = classify_message(hl7_msg, self._mapping_types)

        logger.info(
            "Classified message - MessageId: %s, CorrelationId: %s, TriggerEvent: %s, MappingTypes: %s",
            original_message_id,
            meta["correlation_id"],
            get_trigger_event(hl7_msg),
            mapping_types,
        )

        if not mapping_types:
            error_msg = (
                f"Unsupported message type (trigger event '{get_trigger_event(hl7_msg)}') - "
                f"MessageId: {original_message_id}, CorrelationId: {meta['correlation_id']}"
            )
            logger.error(error_msg)
            self._event_logger.log_message_failed(
                message_body, error_msg, UNSUPPORTED_MESSAGE_REASON, correlation_id=correlation_id
            )
            raise DeadLetterMessage(UNSUPPORTED_MESSAGE_REASON, error_msg)

        failed_paths = [
            mapping_type
            for mapping_type in mapping_types
            if not self._publish_path(
                message_body, incoming_props, mapping_type, original_message_id, correlation_id
            )
        ]
        return not failed_paths

    def _parse_or_dead_letter(
        self, message: ServiceBusMessage, message_body: str, correlation_id: str | None
    ) -> Message:
        try:
            return parse_message(message_body)
        except Exception as e:
            # An unparseable message can never be classified, so retrying it is pointless.
            error_msg = f"Invalid HL7 message - MessageId: {message.message_id}, CorrelationId: {correlation_id}: {e}"
            logger.error(error_msg)
            self._event_logger.log_message_failed(
                message_body, error_msg, INVALID_MESSAGE_REASON, correlation_id=correlation_id
            )
            raise DeadLetterMessage(INVALID_MESSAGE_REASON, error_msg) from e

    @staticmethod
    def _resolve_original_message_id(message: ServiceBusMessage, hl7_msg: Message) -> str:
        if message.message_id:
            return str(message.message_id)
        return str(hl7_msg.msh.msh_10.value or "")

    def _publish_path(
        self,
        message_body: str,
        incoming_props: dict[str, str],
        mapping_type: str,
        original_message_id: str,
        correlation_id: str | None,
    ) -> bool:
        processing_id = str(uuid.uuid4())
        properties = {
            **incoming_props,
            MAPPING_TYPE_KEY: mapping_type,
            PROCESSING_ID_KEY: processing_id,
            ORIGINAL_MESSAGE_ID_KEY: original_message_id,
        }

        try:
            self._sender_client.send_message(
                message_body.encode("utf-8"),
                custom_properties=properties,
                message_id=f"{original_message_id}-{mapping_type}",
            )
        except Exception as e:
            error_msg = (
                f"Failed to publish {mapping_type} path - MessageId: {original_message_id}, "
                f"CorrelationId: {correlation_id}, ProcessingId: {processing_id}: {e}"
            )
            logger.error(error_msg)
            self._event_logger.log_message_failed(
                message_body, error_msg, f"LIMS WRRS publish failed ({mapping_type})", correlation_id=correlation_id
            )
            return False

        logger.info(
            "Published %s path - MessageId: %s, CorrelationId: %s, ProcessingId: %s",
            mapping_type,
            original_message_id,
            correlation_id,
            processing_id,
        )
        self._event_logger.log_message_processed(
            message_body,
            f"LIMS WRRS classified as {mapping_type} (MessageId: {original_message_id}, ProcessingId: {processing_id})",
            correlation_id=correlation_id,
        )
        return True
