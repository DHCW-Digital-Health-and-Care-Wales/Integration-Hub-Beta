from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class EventType(Enum):
    MESSAGE_RECEIVED = "MESSAGE_RECEIVED"
    MESSAGE_PROCESSED = "MESSAGE_PROCESSED"
    MESSAGE_SENT = "MESSAGE_SENT"
    MESSAGE_FAILED = "MESSAGE_FAILED"
    VALIDATION_SUCCESS = "VALIDATION_SUCCESS"
    VALIDATION_FAILED = "VALIDATION_FAILED"


@dataclass(frozen=True)
class LogEvent:
    workflow_id: str
    microservice_id: str
    event_type: EventType
    timestamp: datetime
    message_content: str
    validation_result: Optional[str] = None
    error_details: Optional[str] = None
