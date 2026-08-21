"""Shared type for pluggable payload validators."""
from __future__ import annotations

from typing import Protocol


class Validator(Protocol):
    def validate(self, payload_xml: str, structure_id: str | None) -> None:
        """Raise ``rest_server.errors.ValidationError`` when the payload is invalid."""
        ...
