from dataclasses import dataclass
from typing import Optional


@dataclass
class MessageRecord:
    """Represents a message destined for persistent storage in the monitoring.Message table."""

    received_at: str
    stored_at: str
    correlation_id: str
    source_system: str
    processing_component: str
    target_system: Optional[str]
    raw_payload: str
    xml_payload: Optional[str]


__all__ = ["MessageRecord"]

