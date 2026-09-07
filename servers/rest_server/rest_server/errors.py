"""Error types shared by content adapters, validators and the message processor."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RequestError(Exception):
    """A request-level failure with an HTTP status and adapter-specific fault code."""

    code: str
    message: str
    http_status: int


class ValidationError(Exception):
    """A payload schema/business validation failure - always reported as HTTP 400."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
