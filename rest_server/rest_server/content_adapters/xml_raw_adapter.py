"""Plain XML (no envelope) content adapter - the request body *is* the business payload."""
from __future__ import annotations

from typing import List

from defusedxml.ElementTree import fromstring

from rest_server.errors import RequestError
from rest_server.xml_utils import find_first_text, local_name

from .base import ExtractedPayload


class XmlRawContentAdapter:
    content_type = "application/xml; charset=utf-8"

    def __init__(
        self,
        source_identifier_path: List[str] | None = None,
        message_control_id_path: List[str] | None = None,
    ) -> None:
        self.source_identifier_path = source_identifier_path
        self.message_control_id_path = message_control_id_path

    def extract(self, raw_body: str) -> ExtractedPayload:
        try:
            root = fromstring(raw_body)
        except Exception as exc:
            raise RequestError("Client", "Malformed XML request.", 400) from exc

        source_identifier = (
            find_first_text(root, self.source_identifier_path) if self.source_identifier_path else None
        )
        message_control_id = (
            find_first_text(root, self.message_control_id_path) if self.message_control_id_path else None
        )

        return ExtractedPayload(
            payload_xml=raw_body,
            structure_id=local_name(root.tag),
            source_identifier=source_identifier,
            message_control_id=message_control_id,
        )

    def build_success_response(self, message_control_id: str) -> str:
        escaped = _escape(message_control_id or "")
        return f"<ack><status>Success</status><messageControlId>{escaped}</messageControlId></ack>"

    def build_error_response(self, error_code: str, error_message: str) -> str:
        return f"<error><code>{_escape(error_code)}</code><message>{_escape(error_message)}</message></error>"


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
