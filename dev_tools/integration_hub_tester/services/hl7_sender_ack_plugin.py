"""HL7 Sender — ACK Response plugin.

Previews how hl7_sender/hl7_subscription_sender classify a received ACK/NACK response, using the
real ``ack_processor.get_ack_result()`` — a pure function with no I/O, so it runs unmodified here.

Outcome meaning:
  SUCCESS  MSA-1 = AA/CA               → message send treated as successful
  AE       MSA-1 = AE (or unrecognised) → recoverable — retried per the configured retry policy
  AR       MSA-1 = AR                   → non-recoverable — dead-lettered, not retried
  INVALID  malformed response / no MSA  → treated the same as AE by the caller (see ack_processor)
"""
from __future__ import annotations

from .base import ServicePlugin

_ACK_AA = """\
MSH|^~\\&|MPI|MPI|PIMS|BroMor HL7Sender|20250703120005||ACK^A28^ACK|MSG000002|P|2.5
MSA|AA|MSG000002"""

_NACK_AE = """\
MSH|^~\\&|MPI|MPI|PIMS|BroMor HL7Sender|20250703120005||ACK^A28^ACK|MSG000002|P|2.5
MSA|AE|MSG000002|Temporary application error - please retry"""

_NACK_AR = """\
MSH|^~\\&|MPI|MPI|PIMS|BroMor HL7Sender|20250703120005||ACK^A28^ACK|MSG000002|P|2.5
MSA|AR|MSG000002|Message rejected - patient not found"""

_MALFORMED = "NOT A VALID HL7 ACK RESPONSE"


class Hl7SenderAckPlugin(ServicePlugin):
    tab_label = "HL7 Sender ACK"
    description = (
        "Classify a received ACK/NACK response the way hl7_sender/hl7_subscription_sender do — "
        "SUCCESS (AA/CA) · AE (recoverable, retried) · AR (non-recoverable, dead-lettered) · INVALID"
    )
    input_label = "Simulated ACK/NACK response  (as received back over MLLP)"
    output_label = "Classification"
    button_label = "🔍  Classify Response"
    samples = {
        "AA — success": _ACK_AA,
        "AE — recoverable, retried": _NACK_AE,
        "AR — non-recoverable, dead-lettered": _NACK_AR,
        "Malformed response": _MALFORMED,
    }

    def __init__(self) -> None:
        pass

    def run(self, input_text: str) -> tuple[str, str]:
        from hl7_sender.ack_processor import AckOutcome, get_ack_result

        response = input_text.strip().replace("\n", "\r")
        result = get_ack_result(response)

        lines = [
            "=" * 60,
            "ACK/NACK CLASSIFICATION",
            "=" * 60,
            f"  Outcome        : {result.outcome.value}",
            f"  MSA-1 ack code : {result.ack_code or '(none — unparsable/missing MSA)'}",
            f"  Control ID     : {result.control_id or '(none)'}",
            f"  is_success     : {result.is_success}",
            "",
        ]

        behaviour = {
            AckOutcome.SUCCESS: "✓  Send treated as successful — no retry.",
            AckOutcome.AE: "↻  Recoverable — message will be retried per the configured retry policy.",
            AckOutcome.AR: "☒  Non-recoverable — message is dead-lettered, not retried.",
            AckOutcome.INVALID: "☒  Malformed/unparsable response — treated as a recoverable failure "
            "by the caller (same handling path as AE).",
        }
        lines.append(behaviour[result.outcome])

        status_prefix = "✓" if result.is_success else "✗"
        return "\n".join(lines), f"{status_prefix}  {result.outcome.value}"
