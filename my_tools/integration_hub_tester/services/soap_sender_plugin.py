"""SOAP Sender plugin — build a SOAP envelope and POST it to the mock receiver.

Sends a real HTTP request to the http_mock_receiver (default: http://localhost:8080/soap)
so developers can observe the full round-trip: envelope construction → HTTP POST →
SOAP ACK/fault response — with live output visible in the mock receiver console.

Override the target URL by setting the SOAP_MOCK_URL environment variable.

If the mock receiver is not running, the plugin falls back to offline preview mode
and shows what would have been sent with a clear note at the top.
"""
from __future__ import annotations

import os
import urllib.error
import urllib.request

from .base import ServicePlugin

_SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
_DEFAULT_MOCK_URL = "http://localhost:8080/soap"

_SAMPLE_A01 = """\
MSH|^~\\&|SENDAPP|SENDFAC|RECVAPP|RECVFAC|20250703120000||ADT^A01^ADT_A01|MSG000001|P|2.5
EVN||20250703120000
PID|||1234567890^^^^NH||JONES^GARETH^^^Mr||19800115|M|||10 HIGH STREET^CARDIFF^^CF10 1AA||02920000001^PRN
PV1||I|WARD1^ROOM2^BED3"""

_SAMPLE_A28 = """\
MSH|^~\\&|PIMS|BroMor HL7Sender|MPI|MPI|20250703120000||ADT^A28^ADT_A01|MSG000002|P|2.5
EVN||20250703120000
PID|||9434765919^^^^NH~SB001^^^^PI||BEVAN^ANEURIN^^^Mr||18971115|M|||1 EXAMPLE STREET^^SWANSEA^SA1 1AA
PD1||||G7777777
PV1||U"""

_SAMPLE_FAIL = """\
MSH|^~\\&|SENDAPP|SENDFAC|RECVAPP|RECVFAC|20250703120000||ADT^A01^ADT_A01|MSG_FAIL_01|P|2.5
EVN||20250703120000
PID|||fail^^^^NH||TRIGGER^FAULT^^^Mr||19800115|M
PV1||U"""


class SoapSenderPlugin(ServicePlugin):
    tab_label = "SOAP Sender"
    description = (
        "Send HL7 wrapped in a SOAP envelope to the mock receiver — "
        "start the SOAP Mock Receiver first, then click Send"
    )
    input_label = "HL7v2 ER7  (as it would arrive from the Service Bus queue)"
    output_label = "SOAP Envelope + HTTP Response"
    button_label = "🧼  Send to SOAP Mock"
    samples = {
        "ADT A01 (Inpatient admit)": _SAMPLE_A01,
        "ADT A28 (New patient)": _SAMPLE_A28,
        "Fault trigger (contains 'fail')": _SAMPLE_FAIL,
    }

    def __init__(self) -> None:
        pass

    def run(self, input_text: str) -> tuple[str, str]:
        er7 = input_text.strip().replace("\n", "\r")
        msh_fields = _parse_msh(er7)
        message_control_id = msh_fields.get("control_id", "UNKNOWN")
        message_type = msh_fields.get("message_type", "UNKNOWN")

        envelope = _build_soap_envelope(er7)
        mock_url = os.environ.get("SOAP_MOCK_URL", _DEFAULT_MOCK_URL)

        lines: list[str] = []

        # ── Message summary ───────────────────────────────────────────
        lines.append("=" * 65)
        lines.append("HL7 MESSAGE SUMMARY")
        lines.append("=" * 65)
        lines.append(f"  Message type  : {message_type}")
        lines.append(f"  Control ID    : {message_control_id}")
        lines.append(f"  Version       : {msh_fields.get('version', 'UNKNOWN')}")
        lines.append(f"  Sending app   : {msh_fields.get('sending_app', 'UNKNOWN')}")

        # ── Envelope sent ─────────────────────────────────────────────
        lines.append("")
        lines.append("=" * 65)
        lines.append(f"SOAP ENVELOPE SENT  →  {mock_url}")
        lines.append("=" * 65)
        lines.append(envelope)

        # ── Live POST ─────────────────────────────────────────────────
        lines.append("")
        lines.append("=" * 65)

        status_code, response_body, error = _post_to_mock(envelope, mock_url)

        if error:
            lines.append("MOCK RECEIVER NOT REACHABLE")
            lines.append("=" * 65)
            lines.append(f"  {error}")
            lines.append("")
            lines.append("  ► Start the SOAP Mock Receiver using the toolbar above,")
            lines.append("    then click Send again.")
            output = "\n".join(lines)
            return output, f"✗  Mock receiver not reachable — {error}"

        # Show actual response
        success = _evaluate_response(status_code, response_body)
        result_label = "✓  AA — Message accepted" if success else "✗  FAULT — Message rejected"
        lines.append(f"SOAP RESPONSE  (HTTP {status_code})  —  {result_label}")
        lines.append("=" * 65)
        lines.append(response_body)

        output = "\n".join(lines)
        summary = f"{'✓' if success else '✗'}  HTTP {status_code} — {result_label}  |  control_id={message_control_id}"
        return output, summary


# ── Helpers ──────────────────────────────────────────────────────────────────

def _parse_msh(er7: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in er7.split("\r"):
        if line.startswith("MSH"):
            fields = line.split("|")
            try:
                result["message_type"] = fields[8] if len(fields) > 8 else "UNKNOWN"
                result["control_id"] = fields[9] if len(fields) > 9 else "UNKNOWN"
                result["version"] = fields[11] if len(fields) > 11 else "UNKNOWN"
                result["sending_app"] = fields[2] if len(fields) > 2 else "UNKNOWN"
            except IndexError:
                pass
            break
    return result


def _escape_xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _build_soap_envelope(er7: str) -> str:
    er7_display = er7.replace("\r", "\r\n")
    escaped = _escape_xml(er7_display)
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<soapenv:Envelope xmlns:soapenv="{_SOAP_NS}">\n'
        f"  <soapenv:Header/>\n"
        f"  <soapenv:Body>\n"
        f"    <SendHL7Message>\n"
        f"      <hl7Message>{escaped}</hl7Message>\n"
        f"    </SendHL7Message>\n"
        f"  </soapenv:Body>\n"
        f"</soapenv:Envelope>"
    )


def _post_to_mock(envelope: str, url: str) -> tuple[int, str, str | None]:
    """POST the envelope to the mock receiver using stdlib urllib.

    Returns (status_code, response_body, error_message).
    error_message is None on success.
    """
    try:
        data = envelope.encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "text/xml; charset=utf-8"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace"), None

    except urllib.error.HTTPError as exc:
        # HTTPError still has a body (e.g. SOAP fault with HTTP 500)
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = str(exc)
        return exc.code, body, None

    except urllib.error.URLError as exc:
        return 0, "", f"Connection refused — is the SOAP Mock Receiver running?  ({exc.reason})"

    except TimeoutError:
        return 0, "", "Request timed out after 10 seconds."

    except Exception as exc:  # noqa: BLE001
        return 0, "", f"Unexpected error: {type(exc).__name__}: {exc}"


def _evaluate_response(status_code: int, body: str) -> bool:
    """Mirror soap_ack_processor.get_ack_result for the tester plugin."""
    if status_code not in (200, 202):
        return False
    if "Fault" in body:
        return False
    return True

# SOAP 1.1 namespace — default for NHS Wales integrations until confirmed otherwise.
_SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"

_SAMPLE_A01 = """\
MSH|^~\\&|SENDAPP|SENDFAC|RECVAPP|RECVFAC|20250703120000||ADT^A01^ADT_A01|MSG000001|P|2.5
EVN||20250703120000
PID|||1234567890^^^^NH||JONES^GARETH^^^Mr||19800115|M|||10 HIGH STREET^CARDIFF^^CF10 1AA||02920000001^PRN
PV1||I|WARD1^ROOM2^BED3"""

_SAMPLE_A28 = """\
MSH|^~\\&|PIMS|BroMor HL7Sender|MPI|MPI|20250703120000||ADT^A28^ADT_A01|MSG000002|P|2.5
EVN||20250703120000
PID|||9434765919^^^^NH~SB001^^^^PI||BEVAN^ANEURIN^^^Mr||18971115|M|||1 EXAMPLE STREET^^SWANSEA^SA1 1AA
PD1||||G7777777
PV1||U"""


class SoapSenderPlugin(ServicePlugin):
    tab_label = "SOAP Sender"
    description = (
        "Preview the SOAP envelope that soap_sender would POST to the endpoint "
        "(no connection made — start the SOAP Mock Receiver to test end-to-end)"
    )
    input_label = "HL7v2 ER7  (as it would arrive from the Service Bus queue)"
    output_label = "SOAP Envelope Preview + Breakdown"
    button_label = "🧼  Preview SOAP Envelope"
    samples = {
        "ADT A01 (Inpatient admit)": _SAMPLE_A01,
        "ADT A28 (New patient)": _SAMPLE_A28,
    }

    def __init__(self) -> None:
        pass

    def run(self, input_text: str) -> tuple[str, str]:
        er7 = input_text.strip().replace("\n", "\r")

        # Extract key MSH fields for the summary without importing hl7apy.
        msh_fields = _parse_msh(er7)
        message_control_id = msh_fields.get("control_id", "UNKNOWN")
        message_type = msh_fields.get("message_type", "UNKNOWN")
        sending_app = msh_fields.get("sending_app", "UNKNOWN")
        hl7_version = msh_fields.get("version", "UNKNOWN")

        # Build the SOAP envelope exactly as soap_sender_client will.
        envelope = _build_soap_envelope(er7, message_control_id)
        content_type = "text/xml; charset=utf-8"

        lines: list[str] = []

        # ── Message summary ───────────────────────────────────────────
        lines.append("=" * 65)
        lines.append("HL7 MESSAGE SUMMARY")
        lines.append("=" * 65)
        lines.append(f"  Message type    : {message_type}")
        lines.append(f"  HL7 version     : {hl7_version}")
        lines.append(f"  Sending app     : {sending_app}")
        lines.append(f"  Control ID      : {message_control_id}")
        lines.append(f"  Segment count   : {len([l for l in er7.split(chr(13)) if l.strip()])}")

        # ── HTTP request preview ──────────────────────────────────────
        lines.append("")
        lines.append("=" * 65)
        lines.append("HTTP REQUEST THAT WOULD BE SENT")
        lines.append("=" * 65)
        lines.append("  Method          : POST")
        lines.append("  URL             : <SOAP_ENDPOINT_URL>  (from env)")
        lines.append(f"  Content-Type    : {content_type}")
        lines.append(f"  Body size       : {len(envelope.encode('utf-8')):,} bytes")
        lines.append("")
        lines.append("  Optional headers (when configured):")
        lines.append("    Authorization : Bearer <token>  or  ApiKey <key>")
        lines.append("    SOAPAction    : <action>")

        # ── Envelope breakdown ────────────────────────────────────────
        lines.append("")
        lines.append("=" * 65)
        lines.append("SOAP ENVELOPE STRUCTURE")
        lines.append("=" * 65)
        lines.append(f"  SOAP version    : 1.1")
        lines.append(f"  Namespace       : {_SOAP_NS}")
        lines.append("  Structure:")
        lines.append("    soapenv:Envelope")
        lines.append("      └─ soapenv:Header  (empty)")
        lines.append("      └─ soapenv:Body")
        lines.append("           └─ SendHL7Message")
        lines.append("                └─ hl7Message  (HL7 ER7 payload)")

        # ── Full envelope ─────────────────────────────────────────────
        lines.append("")
        lines.append("=" * 65)
        lines.append("FULL SOAP ENVELOPE")
        lines.append("=" * 65)
        lines.append("")
        lines.append(envelope)

        # ── Expected ACK ──────────────────────────────────────────────
        lines.append("")
        lines.append("=" * 65)
        lines.append("EXPECTED SOAP ACK RESPONSE  (from mock receiver)")
        lines.append("=" * 65)
        lines.append(_expected_ack(message_control_id))

        output = "\n".join(lines)
        return output, f"✓  SOAP envelope preview — {len(envelope.encode('utf-8')):,} bytes"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _parse_msh(er7: str) -> dict[str, str]:
    """Extract common MSH fields from an ER7 string without hl7apy."""
    result: dict[str, str] = {}
    for line in er7.split("\r"):
        if line.startswith("MSH"):
            fields = line.split("|")
            try:
                result["message_type"] = fields[8] if len(fields) > 8 else "UNKNOWN"
                result["control_id"] = fields[9] if len(fields) > 9 else "UNKNOWN"
                result["version"] = fields[11] if len(fields) > 11 else "UNKNOWN"
                result["sending_app"] = fields[2] if len(fields) > 2 else "UNKNOWN"
                result["sending_fac"] = fields[3] if len(fields) > 3 else "UNKNOWN"
            except IndexError:
                pass
            break
    return result


def _escape_xml(text: str) -> str:
    """Minimal XML character escaping for embedding HL7 in a SOAP body."""
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )


def _build_soap_envelope(er7: str, message_control_id: str) -> str:  # noqa: ARG001
    """Build the SOAP 1.1 envelope exactly as soap_sender_client will construct it."""
    # Normalise CR-only line separators for display in the XML body.
    er7_display = er7.replace("\r", "\r\n")
    escaped_payload = _escape_xml(er7_display)
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<soapenv:Envelope xmlns:soapenv="{_SOAP_NS}">\n'
        f"  <soapenv:Header/>\n"
        f"  <soapenv:Body>\n"
        f"    <SendHL7Message>\n"
        f"      <hl7Message>{escaped_payload}</hl7Message>\n"
        f"    </SendHL7Message>\n"
        f"  </soapenv:Body>\n"
        f"</soapenv:Envelope>"
    )


def _expected_ack(message_control_id: str) -> str:
    """Build the SOAP ACK the mock receiver would return on success."""
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<soapenv:Envelope xmlns:soapenv="{_SOAP_NS}">\n'
        f"  <soapenv:Header/>\n"
        f"  <soapenv:Body>\n"
        f"    <AcknowledgementResponse>\n"
        f"      <Status>AA</Status>\n"
        f"      <MessageControlID>{message_control_id}</MessageControlID>\n"
        f"      <Detail>Message accepted by HTTP mock receiver</Detail>\n"
        f"    </AcknowledgementResponse>\n"
        f"  </soapenv:Body>\n"
        f"</soapenv:Envelope>"
    )
