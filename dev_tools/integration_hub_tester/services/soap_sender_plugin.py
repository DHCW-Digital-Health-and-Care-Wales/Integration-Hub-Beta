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

