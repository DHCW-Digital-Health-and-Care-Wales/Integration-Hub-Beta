"""HL7 Sender plugin — preview what the sender would transmit over MLLP.

The hl7_sender and hl7_subscription_sender services are pure forwarders:
they pull an HL7 ER7 from Service Bus and wrap it in MLLP framing before
sending it downstream over TCP.

This plugin shows:
  1.  A parsed message summary (segments, key MSH fields)
  2.  The exact MLLP byte frame that would be transmitted
      (printable form + annotated hex for the control bytes)

No actual network connection is made.
"""
from __future__ import annotations

from .base import ServicePlugin

# MLLP protocol constants  (HL7 Appendix C)
MLLP_START_BLOCK = b"\x0b"    # VT  — marks the start of a message
MLLP_END_BLOCK = b"\x1c"      # FS  — marks the end of a message
MLLP_CARRIAGE_RETURN = b"\r"  # CR  — follows the end block

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


class Hl7SenderPlugin(ServicePlugin):
    tab_label = "HL7 Sender"
    description = "Preview the MLLP frame that the sender would transmit downstream (no connection made)"
    input_label = "HL7v2 ER7  (as it would arrive from the Service Bus queue)"
    output_label = "MLLP Frame Preview + Message Breakdown"
    button_label = "📡  Preview MLLP Frame"
    samples = {
        "ADT A01 (Inpatient admit)": _SAMPLE_A01,
        "ADT A28 (New patient)": _SAMPLE_A28,
    }

    def __init__(self) -> None:
        pass

    def run(self, input_text: str) -> tuple[str, str]:
        from hl7apy.parser import parse_message

        er7 = input_text.strip().replace("\n", "\r")
        msg = parse_message(er7, find_groups=False)

        # Build the MLLP byte stream exactly as hl7_sender_client sends it.
        payload_bytes = er7.encode("utf-8")
        mllp_frame = MLLP_START_BLOCK + payload_bytes + MLLP_END_BLOCK + MLLP_CARRIAGE_RETURN

        lines: list[str] = []

        # ── Message summary ───────────────────────────────────────────
        lines.append("=" * 60)
        lines.append("MESSAGE SUMMARY")
        lines.append("=" * 60)
        try:
            lines.append(f"  Message type  : {msg.msh.msh_9.value}")
            lines.append(f"  Version       : {msg.msh.msh_12.value}")
            lines.append(f"  Sending app   : {msg.msh.msh_3.value}  →  Sending fac: {msg.msh.msh_4.value}")
            lines.append(f"  Receiving app : {msg.msh.msh_5.value}  →  Receiving fac: {msg.msh.msh_6.value}")
            lines.append(f"  Control ID    : {msg.msh.msh_10.value}")
            lines.append(f"  Date/time     : {msg.msh.msh_7.value}")
            lines.append(f"  Segments      : {', '.join(s.name for s in msg.children)}")
        except Exception as exc:  # noqa: BLE001
            lines.append(f"  (could not summarise: {exc})")

        # ── MLLP frame breakdown ──────────────────────────────────────
        lines.append("")
        lines.append("=" * 60)
        lines.append("MLLP BYTE FRAME  (total: {:,} bytes)".format(len(mllp_frame)))
        lines.append("=" * 60)
        lines.append("")
        lines.append("  Byte 0      : 0x0B  ← MLLP Start Block (VT)")
        lines.append(f"  Bytes 1–{len(payload_bytes)}  : HL7 ER7 payload ({len(payload_bytes):,} bytes, UTF-8)")
        lines.append(f"  Byte {len(payload_bytes) + 1}    : 0x1C  ← MLLP End Block (FS)")
        lines.append(f"  Byte {len(payload_bytes) + 2}    : 0x0D  ← Carriage Return")

        # ── HL7 payload as it would be transmitted ────────────────────
        lines.append("")
        lines.append("=" * 60)
        lines.append("HL7 PAYLOAD  (as transmitted — segment separator = CR 0x0D)")
        lines.append("=" * 60)
        lines.append("")
        for segment_line in er7.split("\r"):
            if segment_line.strip():
                lines.append("  " + segment_line)

        # ── Hex dump of control bytes only ───────────────────────────
        lines.append("")
        lines.append("=" * 60)
        lines.append("MLLP CONTROL BYTES (hex)")
        lines.append("=" * 60)
        lines.append(f"  Start : {MLLP_START_BLOCK.hex().upper()}  (0x0B)")
        lines.append(f"  End   : {(MLLP_END_BLOCK + MLLP_CARRIAGE_RETURN).hex().upper()}  (0x1C 0x0D)")

        output = "\n".join(lines)
        return output, f"✓  MLLP frame preview — {len(mllp_frame):,} bytes total"
