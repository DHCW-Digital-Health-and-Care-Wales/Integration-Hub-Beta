from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class AuditEventType(Enum):
    MESSAGE_RECEIVED = "MESSAGE_RECEIVED"
    MESSAGE_PROCESSED = "MESSAGE_PROCESSED"
    MESSAGE_SENT = "MESSAGE_SENT"
    MESSAGE_FAILED = "MESSAGE_FAILED"
    VALIDATION_SUCCESS = "VALIDATION_SUCCESS"
    VALIDATION_FAILED = "VALIDATION_FAILED"


@dataclass(frozen=True)
class AuditEvent:
    workflow_id: str
    microservice_id: str
    event_type: AuditEventType
    timestamp: datetime
    message_content: str
    validation_result: Optional[str] = None
    error_details: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "workflow_id": self.workflow_id,
            "microservice_id": self.microservice_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "message_content": self.message_content,
            "validation_result": self.validation_result,
            "error_details": self.error_details
        }
