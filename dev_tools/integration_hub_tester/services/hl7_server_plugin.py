"""HL7 Server plugin — validate an inbound HL7v2 message and preview the ACK/NACK.

Exercises the same HL7Validator/HL7AckBuilder (AA happy path) and the real ErrorHandler (AR/AE
NACK building/classification) used by the server, without needing a live MLLP port or Service Bus
connection. EventLogger is instantiated normally (no APPLICATIONINSIGHTS_CONNECTION_STRING set
locally, so it safely falls back to standard logging — no network calls).
"""
from __future__ import annotations

from .base import ServicePlugin

_VALID_A28 = """\
MSH|^~\\&|252|252|100|100|20250505232328||ADT^A28^ADT_A05|202505052323326666666666|P|2.5|||||GBR||EN
EVN||20250502102000|20250505232328|||20250505232328
PID|||8888888^^^252^PI~6666666666^^^NHS^NH||MYSURNAME^MYFNAME^MYMNAME^^MR||19870101|M|||ADDRESS1^ADDRESS2^ADDRESS3^ADDRESS4^XX99 9XX^^H|||||||||||||||01
PD1|||^^W99999^|G7777777
PV1||U"""

_VALID_A31 = """\
MSH|^~\\&|192|192|200|200|20250624161510||ADT^A31|369913945290925|P|2.5|||NE|NE
EVN|Sub|20250624161510
PID|1|1000000001^^^^NH|1000000001^^^^NH~B1000001^^^^PAS||TEST^TEST^^^Mrs.||20000101|F|||1 TEST^TEST^TEST^TEST^CF11 9AD||01000000001^PRN|01000000001^WPN||||||||||||||||||1
PD1||||G7000001
PV1||U"""

_WRONG_VERSION = """\
MSH|^~\\&|192|192|200|200|20250624161510||ADT^A31|369913945290925|P|2.3|||NE|NE
EVN|Sub|20250624161510
PID|1|1000000001^^^^NH||TEST^TEST|||F
PV1||U"""

_UNPARSABLE = "THIS IS NOT AN HL7 MESSAGE AT ALL"


class Hl7ServerPlugin(ServicePlugin):
    tab_label = "HL7 Server"
    description = (
        "Validate an inbound HL7v2 message and preview the ACK (AA) / NACK (AR validation "
        "failure, AE parse or unexpected error) the server would return"
    )
    input_label = "Inbound HL7v2 ER7  (as received by the MLLP server)"
    output_label = "Validation Result + ACK/NACK Preview"
    button_label = "🔍  Validate + Preview ACK/NACK"
    samples = {
        "Valid A28 (v2.5)": _VALID_A28,
        "Valid A31 (v2.5)": _VALID_A31,
        "Wrong version (A31 v2.3) → AR NACK": _WRONG_VERSION,
        "Unparsable → AE NACK (generic)": _UNPARSABLE,
    }

    def __init__(self) -> None:
        pass

    def run(self, input_text: str) -> tuple[str, str]:
        import uuid

        from event_logger_lib.event_logger import EventLogger
        from hl7apy.exceptions import HL7apyException
        from hl7apy.parser import parse_message

        from hl7_server.error_handler import ErrorHandler
        from hl7_server.exceptions.validation_exception import ValidationException
        from hl7_server.hl7_ack_builder import HL7AckBuilder
        from hl7_server.hl7_validator import HL7Validator

        er7 = input_text.strip().replace("\n", "\r")
        event_logger = EventLogger(workflow_id="tester-demo", microservice_id="tester-demo")

        lines: list[str] = []

        # ── Parse ────────────────────────────────────────────────────
        try:
            msg = parse_message(er7, find_groups=False)
        except (HL7apyException, ValueError) as exc:
            # Genuine parse failure — same path hl7apy's MLLPRequestHandler routes into
            # ErrorHandler when the raw bytes can't be parsed at all (-> generic AE NACK).
            lines.append("=" * 60)
            lines.append("PARSE FAILURE")
            lines.append("=" * 60)
            lines.append(f"  ✗  {exc}")
            lines += self._nack_preview_lines(ErrorHandler(exc, er7, event_logger))
            return "\n".join(lines), "✗  Could not parse — AE NACK (generic) preview generated"

        # ── Parsed message summary ─────────────────────────────────────
        lines.append("=" * 60)
        lines.append("PARSED MESSAGE SUMMARY")
        lines.append("=" * 60)
        try:
            lines.append(f"  Message type : {msg.msh.msh_9.value}")
            lines.append(f"  Version      : {msg.msh.msh_12.value}")
            lines.append(f"  Sending app  : {msg.msh.msh_3.value}")
            lines.append(f"  Sending fac  : {msg.msh.msh_4.value}")
            lines.append(f"  Control ID   : {msg.msh.msh_10.value}")
            lines.append(f"  Segments     : {', '.join(s.name for s in msg.children)}")
        except Exception as exc:  # noqa: BLE001
            lines.append(f"  (could not summarise: {exc})")

        # ── Validation ────────────────────────────────────────────────
        lines.append("")
        lines.append("=" * 60)
        lines.append("VALIDATION  (no flow-specific rules — generic server check)")
        lines.append("=" * 60)

        validator = HL7Validator(hl7_version="2.5")
        try:
            validator.validate(msg)
        except ValidationException as exc:
            # Real ErrorHandler classification/NACK-building logic (AR — validation failure).
            lines.append(f"  ✗  Validation failed: {exc}")
            lines.append("")
            lines.append("=" * 60)
            lines.append("NACK THAT WOULD BE RETURNED  (AR — Application Reject)")
            lines.append("=" * 60)
            lines += self._nack_preview_lines(ErrorHandler(exc, er7, event_logger))
            return "\n".join(lines), "✗  Validation failed — AR NACK preview generated"
        except Exception as exc:  # noqa: BLE001
            # Any other/unexpected exception during validation also routes through ErrorHandler,
            # but is classified as AE (Application Error) rather than AR.
            lines.append(f"  ✗  Unexpected validation error: {exc}")
            lines.append("")
            lines.append("=" * 60)
            lines.append("NACK THAT WOULD BE RETURNED  (AE — Application Error)")
            lines.append("=" * 60)
            lines += self._nack_preview_lines(ErrorHandler(exc, er7, event_logger))
            return "\n".join(lines), "✗  Unexpected error — AE NACK preview generated"

        lines.append("  ✓  Message passed all validation checks")

        # ── ACK preview ───────────────────────────────────────────────
        lines.append("")
        lines.append("=" * 60)
        lines.append("ACK THAT WOULD BE RETURNED  (AA — Application Accept)")
        lines.append("=" * 60)

        control_id = str(uuid.uuid4()).replace("-", "")[:20]
        try:
            ack = HL7AckBuilder().build_ack(control_id, msg)
            ack_er7 = ack.to_er7().replace("\r", "\n")
            lines.append(ack_er7)
        except Exception as exc:  # noqa: BLE001
            lines.append(f"  (could not build ACK: {exc})")

        output = "\n".join(lines)
        return output, "✓  Valid — ACK preview generated"

    @staticmethod
    def _nack_preview_lines(error_handler: object) -> list[str]:
        """Run the real ErrorHandler.reply() and format its MLLP-framed NACK for display."""
        nack_mllp = error_handler.reply()  # type: ignore[attr-defined]
        nack_er7 = nack_mllp.strip("\x0b\x1c\r\n").replace("\r", "\n")
        return [nack_er7]
