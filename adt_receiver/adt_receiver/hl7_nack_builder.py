import logging
from datetime import datetime

from hl7apy.consts import VALIDATION_LEVEL
from hl7apy.core import Message, Segment
from hl7apy.parser import parse_message

from .hl7_constant import Hl7Constants

logger = logging.getLogger(__name__)

_FALLBACK_CONTROL_ID = "UNKNOWN"


class HL7NackBuilder:
    def build_nack(self, original_msg_str: str) -> Message:
        original_msg, message_control_id = self._try_parse(original_msg_str)

        nack = Message("ACK", validation_level=VALIDATION_LEVEL.STRICT)

        nack.msh.msh_1 = Hl7Constants.FIELD_SEPARATOR
        nack.msh.msh_2 = Hl7Constants.ENCODING_CHARACTERS

        if original_msg:
            nack.msh.msh_3 = original_msg.msh.msh_5.value
            nack.msh.msh_4 = original_msg.msh.msh_6.value
            nack.msh.msh_5 = original_msg.msh.msh_3.value
            nack.msh.msh_6 = original_msg.msh.msh_4.value
            nack.msh.msh_12 = original_msg.msh.msh_12.value

        nack.msh.msh_7 = datetime.now().strftime("%Y%m%d%H%M%S")
        nack.msh.msh_9.message_code = Hl7Constants.ACK_MESSAGE_TYPE_FORMAT
        nack.msh.msh_10 = message_control_id
        nack.msh.msh_11 = Hl7Constants.PROCESSING_ID_PRODUCTION

        msa = Segment("MSA", validation_level=VALIDATION_LEVEL.STRICT)
        msa.msa_1 = Hl7Constants.NACK_CODE_ERROR
        msa.msa_2 = message_control_id
        nack.add(msa)

        return nack

    def _try_parse(self, msg_str: str) -> tuple[Message | None, str]:
        try:
            parsed = parse_message(msg_str, find_groups=False)
            return parsed, parsed.msh.msh_10.value
        except Exception:
            logger.warning("Could not parse original message for NACK; using fallback control ID")
            return None, _FALLBACK_CONTROL_ID
