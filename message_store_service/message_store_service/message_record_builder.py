import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Sequence

from azure.servicebus import ServiceBusMessage

from .message_record import MessageRecord

logger = logging.getLogger(__name__)


def build_message_record(message: ServiceBusMessage) -> MessageRecord:
    message_body = b"".join(message.body).decode("utf-8")

    try:
        data: Dict[str, Any] = json.loads(message_body)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse message body as JSON - invalid JSON format")
        raise ValueError("Invalid JSON in message body") from e

    try:
        received_at = data["received_at"]
        correlation_id = data["correlation_id"]
        source_system = data["source_system"]
        processing_component = data["processing_component"]
        raw_payload = data["raw_payload"]
    except KeyError as e:
        logger.error(
            "Missing required field in message body - CorrelationId: %s, Field: %s",
            correlation_id or "UNKNOWN",
            e,
        )
        raise KeyError(f"Missing required field: {e}") from e

    # Extract optional fields
    target_system = data.get("target_system")
    xml_payload = data.get("xml_payload")

    now = datetime.now(timezone.utc).isoformat()

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
        stored_at=now,
        correlation_id=correlation_id,
        source_system=source_system,
        processing_component=processing_component,
        target_system=target_system,
        raw_payload=raw_payload,
        xml_payload=xml_payload,
    )


def build_message_records(messages: Sequence[ServiceBusMessage]) -> List[MessageRecord]:
    return [build_message_record(msg) for msg in messages]

