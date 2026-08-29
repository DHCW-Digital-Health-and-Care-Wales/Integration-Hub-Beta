"""Common sender protocol and result type shared by MLLP/REST/SOAP clients."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ultra7.models import Endpoint, Message


@dataclass
class SendResult:
    """Outcome of sending a single message to an endpoint."""

    ok: bool
    latency_ms: float
    response_summary: str
    error: str | None = None


class Sender(Protocol):
    """Implemented by each protocol-specific client (MLLP/REST/SOAP)."""

    def send(self, endpoint: Endpoint, message: Message) -> SendResult:
        ...
