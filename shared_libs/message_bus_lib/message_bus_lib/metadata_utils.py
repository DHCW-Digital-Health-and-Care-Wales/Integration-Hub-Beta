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


def get_metadata_log_values(metadata: dict[str, str] | None) -> tuple[str, str, str, str]:
    if not metadata:
        return ("N/A", "N/A", "N/A", "N/A")
    return (
        metadata.get(EVENT_ID_KEY, "N/A"),
        metadata.get(WORKFLOW_ID_KEY, "N/A"),
        metadata.get(SOURCE_SYSTEM_KEY, "N/A"),
        metadata.get(MESSAGE_RECEIVED_AT_KEY, "N/A"),
    )
