"""Shared types for pluggable content adapters (envelope unwrap + response building)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class ExtractedPayload:
    """The business payload extracted from a raw request body, plus routing metadata."""

    payload_xml: str
    structure_id: str | None
    source_identifier: str | None
    message_control_id: str | None


class ContentAdapter(Protocol):
    """Unwraps a raw request body and builds transport-appropriate responses.

    Each concrete adapter owns both the extraction logic (SOAP envelope, plain XML, ...) and the
    response format that matches that transport, so a SOAP caller gets a SOAP fault/ack and a
    plain-XML caller gets a simple XML ack/error - both driven by the same message processor.
    """

    content_type: str

    def extract(self, raw_body: str) -> ExtractedPayload: ...

    def build_success_response(self, message_control_id: str) -> str: ...

    def build_error_response(self, error_code: str, error_message: str) -> str: ...
