import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from hl7apy.core import Message
from hl7apy.parser import parse_message

logger = logging.getLogger(__name__)

# HL7 MSA-1 acknowledgment codes that are treated as recoverable negative acknowledgements -
# the message will be retried according to the configured retry policy.
RECOVERABLE_ACK_CODES = frozenset({"AE"})

# HL7 MSA-1 acknowledgment codes that are treated as non-recoverable negative acknowledgements -
# the message must not be retried automatically and is routed to the dead-letter/escalation path.
NON_RECOVERABLE_ACK_CODES = frozenset({"AR"})


class AckOutcome(Enum):
    SUCCESS = "SUCCESS"  # MSA-1 = AA/CA
    AE = "AE"  # MSA-1 = AE - application error, recoverable, retryable
    AR = "AR"  # MSA-1 = AR - application reject, non-recoverable, dead-lettered
    INVALID = "INVALID"  # Malformed response or missing MSA segment


@dataclass
class AckResult:
    outcome: AckOutcome
    ack_code: Optional[str]
    control_id: Optional[str]
    raw_response: str

    @property
    def is_success(self) -> bool:
        return self.outcome == AckOutcome.SUCCESS


def get_ack_result(response: str) -> AckResult:
    try:
        response_msg: Message = parse_message(response)

        if not response_msg.MSA:
            error = "Received a non-ACK message"
            logger.error(error)
            return AckResult(AckOutcome.INVALID, None, None, response)

        ack_code = response_msg.MSA.acknowledgment_code.value
        logger.debug(f"ACK Code: {ack_code}")

        control_id: Optional[str] = None
        try:
            control_id = response_msg.MSH.message_control_id.value
        except Exception:
            logger.debug("Unable to extract control ID from ACK message")

        if ack_code in ("AA", "CA"):
            logger.info("Valid ACK received.")
            return AckResult(AckOutcome.SUCCESS, ack_code, control_id, response)

        logger.error(f"Negative ACK received: {ack_code} for: {control_id}")

        if ack_code in NON_RECOVERABLE_ACK_CODES:
            return AckResult(AckOutcome.AR, ack_code, control_id, response)

        # AE, and any other unrecognised negative ack code, is treated as recoverable.
        return AckResult(AckOutcome.AE, ack_code, control_id, response)

    except Exception:
        logger.exception("Exception while parsing ACK message")
        return AckResult(AckOutcome.INVALID, None, None, response)
