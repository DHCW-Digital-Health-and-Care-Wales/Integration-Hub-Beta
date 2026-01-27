from datetime import datetime
from hl7apy.consts import VALIDATION_LEVEL
from hl7apy.core import Message, Segment

from training_hl7_server.constants import Hl7Constants


class AckBuilder:
    def build_ack(
            self,
            message_control_id, 
            original_msg, 
            ack_code: str = Hl7Constants.ACK_CODE_ACCEPT,
            error_message: str | None = None
            ) -> Message:
        ack = Message("ACK", validation_level=VALIDATION_LEVEL.STRICT)

        # Build MSH segment
        ack.msh.msh_1 = Hl7Constants.FIELD_SEPARATOR
        ack.msh.msh_2 = Hl7Constants.ENCODING_CHARACTERS
        ack.msh.msh_3 = original_msg.msh.msh_5.value
        ack.msh.msh_4 = original_msg.msh.msh_6.value
        ack.msh.msh_5 = original_msg.msh.msh_3.value
        ack.msh.msh_6 = original_msg.msh.msh_4.value   
        ack.msh.msh_7 = datetime.now().strftime("%Y%m%d%H%M%S")
        ack.msh.msh_9.message_code = Hl7Constants.ACK_MESSAGE_TYPE
        ack.msh.msh_9.trigger_event = original_msg.msh.msh_9.trigger_event.value
        ack.msh.msh_10 = message_control_id
        ack.msh.msh_11 = Hl7Constants.PROCESSING_ID_PRODUCTION
        ack.msh.msh_12 = original_msg.msh.msh_12.value

        # Build MSA segment
        msa = Segment("MSA", validation_level=VALIDATION_LEVEL.STRICT)
        msa.msa_1 = ack_code
        msa.msa_2 = message_control_id
        ack.add(msa)

        if error_message:
            msa.msa_3 = error_message

        return ack