from datetime import datetime

from hl7apy.consts import VALIDATION_LEVEL
from hl7apy.core import Message, Segment

from .hl7_constant import Hl7Constants


class HL7AckBuilder:
    def build_ack(self, message_control_id: str, original_msg: Message) -> Message:
        ack = Message("ACK", validation_level=VALIDATION_LEVEL.STRICT)

        # Build MSH segment
        ack.msh.msh_1 = Hl7Constants.FIELD_SEPARATOR
        ack.msh.msh_2 = Hl7Constants.ENCODING_CHARACTERS
        ack.msh.msh_3 = original_msg.msh.msh_5.value
        ack.msh.msh_4 = original_msg.msh.msh_6.value
        ack.msh.msh_5 = original_msg.msh.msh_3.value
        ack.msh.msh_6 = original_msg.msh.msh_4.value
        ack.msh.msh_7 = datetime.now().strftime("%Y%m%d%H%M%S")
        ack.msh.msh_9.message_code = Hl7Constants.ACK_MESSAGE_TYPE_FORMAT
        ack.msh.msh_9.trigger_event = original_msg.msh.msh_9.trigger_event.value
        ack.msh.msh_9.message_structure = Hl7Constants.ACK_MESSAGE_TYPE_FORMAT
        ack.msh.msh_10 = message_control_id
        ack.msh.msh_11 = Hl7Constants.PROCESSING_ID_PRODUCTION
        ack.msh.msh_12 = original_msg.msh.msh_12.value

        # Build MSA segment
        msa = Segment("MSA", validation_level=VALIDATION_LEVEL.STRICT)
        msa.msa_1 = Hl7Constants.ACK_CODE_ACCEPT
        msa.msa_2 = message_control_id
        ack.add(msa)

        return ack
