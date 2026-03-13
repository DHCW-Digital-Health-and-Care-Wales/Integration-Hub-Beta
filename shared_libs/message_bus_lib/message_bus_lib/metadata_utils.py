from typing import Any

from azure.servicebus import ServiceBusMessage

NA = "N/A"

CORRELATION_ID_KEY = "CorrelationId"
MESSAGE_RECEIVED_AT_KEY = "MessageReceivedAt"
SOURCE_SYSTEM_KEY = "SourceSystem"
WORKFLOW_ID_KEY = "WorkflowID"

METADATA_FIELD_MAP = {
    "correlation_id": CORRELATION_ID_KEY,
    "workflow_id": WORKFLOW_ID_KEY,
    "source_system": SOURCE_SYSTEM_KEY,
    "message_received_at": MESSAGE_RECEIVED_AT_KEY,
}


def _to_str(value: str | bytes | int | float | bool | object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _read_application_properties(message: ServiceBusMessage) -> dict[Any, Any] | None:
    direct_props = getattr(message, "application_properties", None)
    if direct_props:
        return direct_props

    raw_amqp_message = getattr(message, "raw_amqp_message", None)
    if raw_amqp_message is None:
        return None

    raw_props = getattr(raw_amqp_message, "application_properties", None)
    return raw_props if raw_props else None


def extract_metadata(message: ServiceBusMessage) -> dict[str, str] | None:
    props = _read_application_properties(message) or {}
    if not props:
        return None

    metadata = {_to_str(k): _to_str(v) for k, v in props.items()}

    return metadata or None


def get_metadata_log_values(metadata: dict[str, str] | None) -> dict[str, str]:
    metadata = metadata or {}

    return {log_key: metadata.get(app_prop_key, NA) for log_key, app_prop_key in METADATA_FIELD_MAP.items()}


def correlation_id_for_logger(meta: dict[str, str]) -> str | None:
    """
    Return correlation_id for EventLogger (None when missing or N/A).
    """
    value = meta.get("correlation_id", NA)
    return None if value == NA else value
