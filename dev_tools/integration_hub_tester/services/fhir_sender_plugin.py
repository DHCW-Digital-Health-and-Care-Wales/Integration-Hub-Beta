"""FHIR Sender plugin — run the real FhirSenderClient against the mock Promptly API.

Start the "SOAP Mock Receiver (port 8080)" from the toolbar first: the same http_mock_receiver
serves ``POST /fhir/r4/$process-message`` and ``GET /fhir/r4/status/{id}``. The mock picks a
scenario from ``Bundle.id`` (``mock-400``, ``mock-429-once`` ...; see fhir_handler.py).

Override the target with the FHIR_MOCK_URL environment variable.
"""
from __future__ import annotations

import json
import os
from typing import Any

import requests
from fhir_sender.auth import ApiKeyAuth
from fhir_sender.errors import (
    AuthorizationDeliveryError,
    DeliveryError,
    PermanentDeliveryError,
    TransientDeliveryError,
)
from fhir_sender.fhir_sender_client import FhirSenderClient

from .base import ServicePlugin

_DEFAULT_MOCK_URL = "http://localhost:8080/fhir/r4/$process-message"
_MAX_BODY_CHARS = 600


def _bundle(bundle_id: str) -> str:
    return json.dumps(
        {
            "resourceType": "Bundle",
            "id": bundle_id,
            "type": "message",
            "entry": [
                {
                    "fullUrl": "urn:uuid:11111111-1111-1111-1111-111111111111",
                    "resource": {
                        "resourceType": "MessageHeader",
                        "eventCoding": {"system": "https://example.test/events", "code": "referral-created"},
                    },
                }
            ],
        },
        indent=2,
    )


class FhirSenderPlugin(ServicePlugin):
    tab_label = "FHIR Sender"
    description = (
        "Send a FHIR message Bundle through the real FhirSenderClient to the mock Promptly API — "
        "start the mock receiver first. Bundle.id selects the scenario."
    )
    input_label = "FHIR message Bundle JSON  (Bundle.id 'mock-…' picks the mock scenario)"
    output_label = "HTTP traffic + Service Bus outcome"
    button_label = "🔥  Send to Promptly Mock"
    samples = {
        "Success (async: 202 → polls → 200)": _bundle("success-001"),
        "Slow processing (6 polls)": _bundle("mock-slow"),
        "Error OperationOutcome on 200 → dead-letter": _bundle("mock-error-outcome"),
        "400 Bad Request → dead-letter": _bundle("mock-400"),
        "Status poll returns 400 → dead-letter": _bundle("mock-status-400"),
        "401 Unauthorized → alert + abandon": _bundle("mock-401"),
        "403 Forbidden → alert + abandon": _bundle("mock-403"),
        "409 Conflict → dead-letter (no retry)": _bundle("mock-409"),
        "429 once → Retry-After then success": _bundle("mock-429-once"),
        "500 once → backoff then success": _bundle("mock-500-once"),
        "500 always → retries exhausted, abandon": _bundle("mock-500"),
    }

    def __init__(self) -> None:
        pass

    def run(self, input_text: str) -> tuple[str, str]:
        text = input_text.strip()
        if not text:
            raise ValueError("Paste a FHIR Bundle JSON first")
        try:
            parsed = json.loads(text)
        except ValueError as exc:
            raise ValueError(f"Input is not valid JSON: {exc}") from exc
        if not isinstance(parsed, dict) or parsed.get("resourceType") != "Bundle" or parsed.get("type") != "message":
            raise ValueError("Input must be a Bundle with type 'message'")

        url = os.environ.get("FHIR_MOCK_URL", _DEFAULT_MOCK_URL)
        traffic: list[str] = []
        session = requests.Session()
        session.hooks["response"].append(lambda resp, *_, **__: traffic.append(_describe(resp)))
        client = FhirSenderClient(
            endpoint_url=url,
            auth=ApiKeyAuth("tester-api-key"),
            timeout_seconds=10,
            max_attempts=3,
            backoff_seconds=0.5,
            max_retry_after_seconds=2,
            poll_interval_seconds=0.5,
            poll_timeout_seconds=15,
            allow_insecure_http=True,
            session=session,
        )

        try:
            client.send_bundle(text)
            outcome = "✓  Delivered → COMPLETE the Service Bus message"
        except PermanentDeliveryError as exc:
            outcome = f"✗  Rejected by Promptly → DEAD-LETTER ('PromptlyRejected')\n   {exc}"
        except AuthorizationDeliveryError as exc:
            outcome = f"✗  Authorisation failure → ALERT + ABANDON (message stays queued)\n   {exc}"
        except TransientDeliveryError as exc:
            if not traffic:
                return self._not_reachable(url, exc)
            outcome = f"✗  Not confirmed after retries → ABANDON (redelivered later)\n   {exc}"
        except DeliveryError as exc:
            outcome = f"✗  {type(exc).__name__}: {exc}"

        lines = [f"TARGET: {url}", "", "HTTP TRAFFIC (in order)", "=" * 65, *traffic, "", "OUTCOME", "=" * 65, outcome]
        return "\n".join(lines), outcome.splitlines()[0]

    @staticmethod
    def _not_reachable(url: str, exc: Exception) -> tuple[str, str]:
        msg = f"Mock receiver not reachable at {url} — start the mock receiver from the toolbar.\n  {exc}"
        return msg, "✗  Mock receiver not reachable"


def _describe(resp: requests.Response) -> str:
    req: Any = resp.request
    interesting = {k: v for k, v in resp.headers.items() if k.lower() in ("content-location", "retry-after", "x-progress")}
    body = resp.text[:_MAX_BODY_CHARS]
    head = f"{req.method} {req.url}  →  HTTP {resp.status_code}"
    if interesting:
        head += "  " + ", ".join(f"{k}: {v}" for k, v in interesting.items())
    return head + (f"\n    {body}" if body else "")
