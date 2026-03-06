import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Sequence

from azure.servicebus import ServiceBusMessage

from .message_record import MessageRecord

logger = logging.getLogger(__name__)


def build_message_record(message: ServiceBusMessage) -> MessageRecord:
    message_body = b"".join(message.body).decode("utf-8")

    try:
        data: Dict[str, Any] = json.loads(message_body)
    except json.JSONDecodeError as e:
        logger.exception("Failed to parse message body as JSON - invalid JSON format")
        raise ValueError("Invalid JSON in message body") from e

    correlation_id: str | None = None

    try:
        received_at_str = data["MessageReceivedAt"]
        correlation_id = data["CorrelationId"]
        source_system = data["SourceSystem"]
        processing_component = data["ProcessingComponent"]
        raw_payload = data["RawPayload"]
    except KeyError as e:
        logger.exception(
            "Missing required field in message body - CorrelationId: %s",
            correlation_id or "UNKNOWN",
        )
        raise KeyError(f"Missing required field: {e}") from e

    try:
        received_at = datetime.fromisoformat(received_at_str)
    except ValueError as e:
        logger.exception(
            "Invalid received_at timestamp format — CorrelationId: %s, Value: %s",
            correlation_id,
            received_at_str,
        )
        raise ValueError(f"Invalid received_at timestamp: {received_at_str!r}") from e

    # Extract optional fields
    target_system = data.get("TargetSystem")
    xml_payload = data.get("XmlPayload")

    logger.debug(
        "Building record — CorrelationId: %s, SourceSystem: %s, ProcessingComponent: %s, "
        "TargetSystem: %s, ReceivedAt: %s",
        correlation_id,
        source_system,
        processing_component,
        target_system,
        received_at,
    )

    return MessageRecord(
        received_at=received_at,
        correlation_id=correlation_id,
        source_system=source_system,
        processing_component=processing_component,
        target_system=target_system,
        raw_payload=raw_payload,
        xml_payload=xml_payload,
    )


def build_message_records(messages: Sequence[ServiceBusMessage]) -> List[MessageRecord]:
    return [build_message_record(msg) for msg in messages]

