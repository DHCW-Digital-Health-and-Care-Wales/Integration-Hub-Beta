"""HL7 Server plugin — validate an inbound HL7v2 message and preview the ACK.

Exercises the same HL7Validator and HL7AckBuilder used by the real server,
without needing a live MLLP port or Service Bus connection.
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


class Hl7ServerPlugin(ServicePlugin):
    tab_label = "HL7 Server"
    description = "Validate an inbound HL7v2 message and preview the ACK the server would return"
    input_label = "Inbound HL7v2 ER7  (as received by the MLLP server)"
    output_label = "Validation Result + ACK Preview"
    button_label = "🔍  Validate + Preview ACK"
    samples = {
        "Valid A28 (v2.5)": _VALID_A28,
        "Valid A31 (v2.5)": _VALID_A31,
        "Wrong version (A31 v2.3)": _WRONG_VERSION,
    }

    def __init__(self) -> None:
        pass

    def run(self, input_text: str) -> tuple[str, str]:
        import uuid

        from hl7apy.parser import parse_message

        from hl7_server.hl7_ack_builder import HL7AckBuilder
        from hl7_server.hl7_validator import HL7Validator
        from hl7_server.exceptions.validation_exception import ValidationException

        er7 = input_text.strip().replace("\n", "\r")
        msg = parse_message(er7, find_groups=False)

        lines: list[str] = []

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

        validation_ok = True
        validator = HL7Validator()
        try:
            validator.validate(msg)
            lines.append("  ✓  Message passed all validation checks")
        except ValidationException as exc:
            validation_ok = False
            lines.append(f"  ✗  Validation failed: {exc}")
        except Exception as exc:  # noqa: BLE001
            validation_ok = False
            lines.append(f"  ✗  Unexpected validation error: {exc}")

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
        status = "✓  Valid — ACK preview generated" if validation_ok else "✗  Validation failed — see output"
        return output, status
