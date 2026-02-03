from azure.servicebus import ServiceBusMessage

EVENT_ID_KEY = "EventId"
WORKFLOW_ID_KEY = "WorkflowID"
SOURCE_SYSTEM_KEY = "SourceSystem"
MESSAGE_RECEIVED_AT_KEY = "MessageReceivedAt"

METADATA_KEYS = (EVENT_ID_KEY, WORKFLOW_ID_KEY, SOURCE_SYSTEM_KEY, MESSAGE_RECEIVED_AT_KEY)


def extract_metadata(message: ServiceBusMessage) -> dict[str, str] | None:
    props = message.application_properties
    if not props:
        return None
    result = {}
    for k, v in props.items():
        result[k.decode("utf-8") if isinstance(k, bytes) else str(k)] = (
            v.decode("utf-8") if isinstance(v, bytes) else str(v)
        )
    return result if result else None


def get_metadata_log_values(metadata: dict[str, str] | None) -> dict[str, str]:
    if not metadata:
        return {
            "event_id": "N/A",
            "workflow_id": "N/A",
            "source_system": "N/A",
            "message_received_at": "N/A",
        }
    return {
        "event_id": metadata.get(EVENT_ID_KEY, "N/A"),
        "workflow_id": metadata.get(WORKFLOW_ID_KEY, "N/A"),
        "source_system": metadata.get(SOURCE_SYSTEM_KEY, "N/A"),
        "message_received_at": metadata.get(MESSAGE_RECEIVED_AT_KEY, "N/A"),
    }


def event_id_for_logger(meta: dict[str, str]) -> str | None:
    """Return event_id for EventLogger (None when missing or N/A)."""
    v = meta.get("event_id", "N/A")
    return v if v != "N/A" else None
