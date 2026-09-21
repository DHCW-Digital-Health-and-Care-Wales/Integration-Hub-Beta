"""REST Server plugin (`hl7` pipeline) — validate + preview the ACK/NACK for a JSON HL7 POST.

Runs the real ``Hl7MessageProcessor.process()`` pipeline used by ``servers/rest_server`` (the
current, actively-developed successor to the retired ``hl7_rest_server`` service — see
servers/rest_server/README.md). Only the outbound I/O boundary is stubbed out with no-op mocks
(Service Bus sender, message store) so no network calls are made; validation, ACK/NACK building
and error classification are the real production code, unmodified.

Preview is limited to the ``hl7`` pipeline with no flow (``HL7_VALIDATION_FLOW`` unset) — the
simplest configuration recipe in the README. The ``generic``/SOAP/XML-raw pipeline and the `mpi`/
`risp` flow-specific rules are not covered by this tab.
"""
from __future__ import annotations

import json

from .base import ServicePlugin

_VALID_A28 = """\
MSH|^~\\&|252|252|100|100|20250505232328||ADT^A28^ADT_A05|202505052323326666666666|P|2.5|||||GBR||EN
EVN||20250502102000|20250505232328|||20250505232328
PID|||8888888^^^252^PI~6666666666^^^NHS^NH||MYSURNAME^MYFNAME^MYMNAME^^MR||19870101|M|||ADDRESS1^ADDRESS2^ADDRESS3^ADDRESS4^XX99 9XX^^H|||||||||||||||01
PD1|||^^W99999^|G7777777
PV1||U"""

_MALFORMED = "THIS IS NOT AN HL7 MESSAGE"


class RestServerPlugin(ServicePlugin):
    tab_label = "REST Server (HL7)"
    description = (
        "POST /hl7MessageReceiver {\"messageContent\": \"...\"}  →  HL7 ACK (201) / NACK (422/500)  "
        "— rest_server 'hl7' pipeline, no flow  ⚠ supersedes the retired hl7_rest_server service"
    )
    input_label = "Inbound HL7v2 ER7  (JSON messageContent body, shown as raw ER7 here)"
    output_label = "HTTP status + ACK/NACK body"
    button_label = "🔍  Validate + Preview ACK"
    samples = {
        "Valid A28 (v2.5)": _VALID_A28,
        "Malformed (unparsable)": _MALFORMED,
    }

    def __init__(self) -> None:
        pass

    def run(self, input_text: str) -> tuple[str, str]:
        from unittest.mock import MagicMock

        from rest_server.hl7.errors import Hl7ParseError, Hl7ValidationError
        from rest_server.hl7.hl7_ack_builder import HL7AckBuilder
        from rest_server.hl7.hl7_message_processor import Hl7MessageProcessor
        from rest_server.hl7.hl7_validator import HL7Validator

        # Simulate the JSON envelope real callers POST, so the sample reflects the actual API
        # contract even though only the ER7 payload is meaningful to the pipeline below.
        request_body = json.dumps({"messageContent": input_text.strip()})

        processor = Hl7MessageProcessor(
            sender_client=MagicMock(),
            event_logger=MagicMock(),
            metric_sender=MagicMock(),
            validator=HL7Validator(),
            message_store_client=MagicMock(),
            ack_builder=HL7AckBuilder(),
            workflow_id="tester-demo",
            egress_session_id="tester-demo-session",
        )

        lines = ["=" * 60, "REQUEST BODY  POST /hl7MessageReceiver", "=" * 60, request_body, ""]

        try:
            ack = processor.process(input_text.strip())
            lines += ["=" * 60, "201 Created — ACK", "=" * 60, ack]
            return "\n".join(lines), "✓  201 — AA ACK generated"
        except Hl7ValidationError as exc:
            lines += ["=" * 60, f"422 Unprocessable Entity — NACK  ({exc.reason})", "=" * 60, exc.nack_message]
            return "\n".join(lines), f"✗  422 — validation failed: {exc.reason}"
        except Hl7ParseError as exc:
            lines += ["=" * 60, f"500 Internal Server Error  ({exc.reason})", "=" * 60]
            return "\n".join(lines), f"✗  500 — could not parse message: {exc.reason}"
