"""HL7 SOAP Server plugin — unwrap, XSD-validate and preview the SOAP ACK/fault response.

Runs the real ``SoapMessageProcessor.process()`` from ``servers/hl7_soap_server`` (unwrap SOAP
envelope, allowed-structure check, XSD schema validation, assigning-authority check, ER7
conversion). Only the outbound I/O boundary is stubbed out with no-op mocks (Service Bus sender,
event logger, metric sender, message store) — this is the exact pattern the service's own test
suite uses (see tests/test_soap_processor.py), so no network calls are made and the validation/
response-building logic is unmodified production code.

Fixed for this preview: schema_group="phw", allowed_hl7_structures=["ADT_A05", "ADT_A39"],
allowed_assigning_authorities=["328"] — matching the PHW SOAP configuration recipe. Input is ER7
(converted to HL7 v2.xml and wrapped in a SOAP envelope here) for readability; real callers POST
the SOAP+XML envelope directly.
"""
from __future__ import annotations

from .base import ServicePlugin

_VALID_A05 = """\
MSH|^~\\&|328|328|100|100|20260729095037||ADT^A28^ADT_A05|6778031837018553261z82215|P|2.5|||||GBR||EN
EVN|A28|20260729095037|20260729095037|||20260729095037
PID|||B0000010612^^^328^PI||LIMS^TEST
PV1||"""

_WRONG_STRUCTURE = "<not-a-valid-soap-request"

_UNKNOWN_AUTHORITY = """\
MSH|^~\\&|999|999|100|100|20260729095037||ADT^A28^ADT_A05|6778031837018553261z82217|P|2.5|||||GBR||EN
EVN|A28|20260729095037|20260729095037|||20260729095037
PID|||B0000010612^^^999^PI||LIMS^TEST
PV1||"""

_SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"


class HL7SoapServerPlugin(ServicePlugin):
    tab_label = "HL7 SOAP Server"
    description = (
        "POST SOAP+HL7v2.xml envelope → SOAP AckResponse (200) / SOAP Fault (400/403/500)  — "
        "hl7_soap_server, schema_group='phw', structures=ADT_A05/ADT_A39, authority='328'"
    )
    input_label = "Inbound HL7v2 ER7  (converted to v2.xml + wrapped in a SOAP envelope here)"
    output_label = "SOAP response envelope (AckResponse or Fault)"
    button_label = "🔍  Validate + Preview SOAP response"
    samples = {
        "Valid ADT_A05 (authority 328)": _VALID_A05,
        "Malformed SOAP request": _WRONG_STRUCTURE,
        "Unknown assigning authority (999)": _UNKNOWN_AUTHORITY,
    }

    def __init__(self) -> None:
        pass

    def run(self, input_text: str) -> tuple[str, str]:
        from unittest.mock import MagicMock

        from hl7_validation import convert_er7_to_xml_with_flow_schema

        from hl7_soap_server.soap_processor import SoapMessageProcessor

        stripped = input_text.strip()

        if stripped.startswith("<"):
            # Already a raw SOAP/XML body (e.g. the malformed sample) — send as-is, skipping the
            # ER7 -> HL7 v2.xml -> SOAP-envelope build below.
            soap_request = stripped
        else:
            er7 = stripped.replace("\n", "\r")
            try:
                payload_xml = convert_er7_to_xml_with_flow_schema(er7, "phw")
            except Exception as exc:  # noqa: BLE001
                return "", f"✗  Could not convert ER7 to HL7 v2.xml: {exc}"

            soap_request = (
                f'<SOAP-ENV:Envelope xmlns:SOAP-ENV="{_SOAP_NS}">'
                "<SOAP-ENV:Body>"
                f"{payload_xml}"
                "</SOAP-ENV:Body>"
                "</SOAP-ENV:Envelope>"
            )

        processor = SoapMessageProcessor(
            sender_client=MagicMock(),
            event_logger=MagicMock(),
            metric_sender=MagicMock(),
            message_store_client=MagicMock(),
            workflow_id="tester-demo",
            egress_session_id="tester-demo-session",
            schema_group="phw",
            allowed_hl7_structures=["ADT_A05", "ADT_A39"],
            allowed_assigning_authorities=["328"],
        )

        status_code, response_xml = processor.process(soap_request)

        lines = ["=" * 60, "SOAP REQUEST (as sent to the server)", "=" * 60, soap_request, "",
                 "=" * 60, f"HTTP {status_code} — SOAP RESPONSE", "=" * 60, response_xml]
        status = f"✓  {status_code} OK" if status_code == 200 else f"✗  HTTP {status_code} — see output"
        return "\n".join(lines), status
