"""FHIR JSON content adapter - the request body *is* a single FHIR resource (no envelope).

SPIKE (INTHUB-590477): proof-of-concept scaffolding only, not yet wired into a deployed
configuration recipe. ``ExtractedPayload.payload_xml`` is XML-shaped for historical reasons (the
``generic`` pipeline started out XML-only) - here it carries the raw FHIR JSON string unchanged.
If this graduates past spike, consider generalising ``ExtractedPayload`` with a
``content_format: Literal["xml", "json"]`` field instead of overloading the XML-named attribute.
"""
from __future__ import annotations

import json
from typing import Any

from rest_server.errors import RequestError

from .base import ExtractedPayload


class FhirJsonContentAdapter:
    content_type = "application/fhir+json; charset=utf-8"

    def extract(self, raw_body: str) -> ExtractedPayload:
        try:
            data = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise RequestError("Client", "Malformed JSON request.", 400) from exc

        if not isinstance(data, dict):
            raise RequestError("Client", "FHIR request body must be a JSON object.", 400)

        resource_type = data.get("resourceType")
        if not isinstance(resource_type, str) or not resource_type:
            raise RequestError("Client", "FHIR resource has a missing or invalid 'resourceType'.", 400)

        return ExtractedPayload(
            payload_xml=raw_body,
            structure_id=resource_type,
            source_identifier=_extract_source_identifier(data),
            message_control_id=data.get("id"),
        )

    def build_success_response(self, message_control_id: str) -> str:
        outcome = {
            "resourceType": "OperationOutcome",
            "issue": [
                {
                    "severity": "information",
                    "code": "informational",
                    "diagnostics": f"Resource accepted (id: {message_control_id})" if message_control_id
                    else "Resource accepted.",
                }
            ],
        }
        return json.dumps(outcome)

    def build_error_response(self, error_code: str, error_message: str) -> str:
        outcome = {
            "resourceType": "OperationOutcome",
            "issue": [
                {
                    "severity": "error",
                    "code": _issue_code_for(error_code),
                    "diagnostics": error_message,
                }
            ],
        }
        return json.dumps(outcome)


def _extract_source_identifier(data: dict[str, Any]) -> str | None:
    """Best-effort source identifier lookup - ``Bundle.meta.source``, or a ``MessageHeader``'s
    sending endpoint, since FHIR has no single universal "sending system" field like HL7 MSH.3/4.
    """
    meta = data.get("meta")
    if isinstance(meta, dict) and isinstance(meta.get("source"), str):
        return meta["source"]

    if data.get("resourceType") == "MessageHeader":
        source = data.get("source")
        if isinstance(source, dict) and isinstance(source.get("endpoint"), str):
            return source["endpoint"]

    return None


def _issue_code_for(error_code: str) -> str:
    """Map our internal fault codes to the closest FHIR OperationOutcome issue type code."""
    if error_code.startswith("Client.Validation"):
        return "structure"
    if error_code.startswith("Client.Authorization"):
        return "forbidden"
    if error_code.startswith("Client"):
        return "invalid"
    return "processing"
