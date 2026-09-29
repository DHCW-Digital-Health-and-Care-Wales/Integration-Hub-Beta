"""FHIR Server plugin (spike INTHUB-590477) — validate + preview the response for a FHIR POST.

Runs the real ``rest_server`` 'generic' pipeline configured as CONTENT_ADAPTER=fhir-json,
VALIDATOR_TYPE=fhir (``FhirJsonContentAdapter`` + ``FhirResourceValidator`` +
``RestMessageProcessor``) — production code, unmodified. Only the outbound I/O boundary is
stubbed out with no-op mocks (Service Bus sender, event logger, metric sender, message store) so
no network calls are made.

This is spike scaffolding, not yet a deployed configuration recipe — see
servers/rest_server/examples/fhir-json.env.example and the spike findings for context.
Structural validation only (via fhir.resources): no profile/StructureDefinition or terminology
(ValueSet/CodeSystem) checks are performed.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from rest_server.content_adapters.fhir_json_adapter import FhirJsonContentAdapter
from rest_server.message_processor import RestMessageProcessor
from rest_server.validators.fhir_validator import FhirResourceValidator

from .base import ServicePlugin

_VALID_BUNDLE = """{
  "resourceType": "Bundle",
  "id": "example-bundle-1",
  "type": "message",
  "meta": {"source": "urn:dhcw:cdr"},
  "entry": []
}"""

_DISALLOWED_RESOURCE_TYPE = """{
  "resourceType": "Patient",
  "id": "example-patient-1"
}"""

_MALFORMED_JSON = "{ this is not valid json"


class FhirServerPlugin(ServicePlugin):
    tab_label = "FHIR Server (spike)"
    description = (
        "POST <FHIR JSON resource>  →  200 OperationOutcome (accepted) / 400/403/500 OperationOutcome "
        "(rejected)  — rest_server 'generic' pipeline, CONTENT_ADAPTER=fhir-json, VALIDATOR_TYPE=fhir  "
        "⚠ spike INTHUB-590477 — structural validation only, not yet a deployed configuration"
    )
    input_label = "Inbound FHIR resource (raw JSON body)"
    output_label = "HTTP status + OperationOutcome body"
    button_label = "🔍  Validate + Preview Response"
    samples = {
        "Valid Bundle": _VALID_BUNDLE,
        "Disallowed resourceType (Patient)": _DISALLOWED_RESOURCE_TYPE,
        "Malformed JSON": _MALFORMED_JSON,
    }

    def __init__(self) -> None:
        pass

    def run(self, input_text: str) -> tuple[str, str]:
        processor = RestMessageProcessor(
            content_adapter=FhirJsonContentAdapter(),
            validator=FhirResourceValidator(allowed_resource_types=["Bundle"]),
            sender_client=MagicMock(),
            event_logger=MagicMock(),
            metric_sender=MagicMock(),
            message_store_client=MagicMock(),
            workflow_id="tester-demo",
            egress_session_id="tester-demo-session",
            allowed_source_identifiers=[],
            output_format="raw",
        )

        raw_body = input_text.strip()
        lines = ["=" * 60, "REQUEST BODY  POST /fhir", "=" * 60, raw_body, ""]

        status_code, response_body = processor.process(raw_body)
        lines += ["=" * 60, f"{status_code} — response", "=" * 60, response_body]

        if status_code == 200:
            return "\n".join(lines), "✓  200 — accepted"
        return "\n".join(lines), f"✗  {status_code} — rejected"
