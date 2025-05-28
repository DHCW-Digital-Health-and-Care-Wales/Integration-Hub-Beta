from hl7apy.core import Message, Segment
from hl7apy.consts import VALIDATION_LEVEL
from datetime import datetime


class HL7AckBuilder:
    def __init__(self, sending_app='100', sending_fac='100', receiving_app='252', receiving_fac='252', version='2.5'):
        self.sending_app = sending_app
        self.sending_fac = sending_fac
        self.receiving_app = receiving_app
        self.receiving_fac = receiving_fac
        self.version = version

    def build_ack(self, message_control_id: str, message_type: str = "A31") -> Message:
        ack = Message("ACK", validation_level=VALIDATION_LEVEL.STRICT)

        # Build MSH segment
        ack.msh.msh_1 = '|'
        ack.msh.msh_2 = '^~\\&'
        ack.msh.msh_3 = self.sending_app
        ack.msh.msh_4 = self.sending_fac
        ack.msh.msh_5 = self.receiving_app
        ack.msh.msh_6 = self.receiving_fac
        ack.msh.msh_7 = datetime.now().strftime('%Y%m%d%H%M%S')
        ack.msh.msh_9 = f'ACK^{message_type}^ACK'
        ack.msh.msh_10 = message_control_id
        ack.msh.msh_11 = 'P'
        ack.msh.msh_12 = self.version

        # Build MSA segment
        msa = Segment("MSA", validation_level=VALIDATION_LEVEL.STRICT)
        msa.msa_1 = "AA"
        msa.msa_2 = message_control_id
        ack.add(msa)

        return ack

    def to_mllp(self, hl7_message: Message) -> str:
        return f'\x0b{hl7_message.to_er7()}\x1c\r'
