from azure.servicebus import ServiceBusMessage

NA = "N/A"

METADATA_FIELD_MAP = {
    "event_id": "EventId",
    "workflow_id": "WorkflowID",
    "source_system": "SourceSystem",
    "message_received_at": "MessageReceivedAt",
}


def _to_str(value: str | bytes | int | float | bool | object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def extract_metadata(message: ServiceBusMessage) -> dict[str, str] | None:
    props = message.application_properties or {}
    if not props:
        return None

    metadata = {_to_str(k): _to_str(v) for k, v in props.items()}

    return metadata or None


def get_metadata_log_values(metadata: dict[str, str] | None) -> dict[str, str]:
    metadata = metadata or {}

    return {log_key: metadata.get(app_prop_key, NA) for log_key, app_prop_key in METADATA_FIELD_MAP.items()}


def event_id_for_logger(meta: dict[str, str]) -> str | None:
    """
    Return event_id for EventLogger (None when missing or N/A).
    """
    value = meta.get("event_id", NA)
    return None if value == NA else value
