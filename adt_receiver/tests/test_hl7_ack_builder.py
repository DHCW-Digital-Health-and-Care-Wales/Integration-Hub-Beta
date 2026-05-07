import unittest

from hl7apy.parser import parse_message

from adt_receiver.hl7_ack_builder import HL7AckBuilder
from adt_receiver.hl7_constant import Hl7Constants

VALID_ADT_MESSAGE = (
    "MSH|^~\\&|SENDER|FAC_SEND|RECEIVER|FAC_RECV|20250506120000||ADT^A01^ADT_A01|CTRL001|P|2.5\r"
    "PID|1||12345^^^Hospital^MR||Smith^John\r"
)


class TestHL7AckBuilder(unittest.TestCase):

    def setUp(self) -> None:
        self.builder = HL7AckBuilder()
        self.original_msg = parse_message(VALID_ADT_MESSAGE, find_groups=False)

    def test_build_ack_returns_message(self) -> None:
        ack = self.builder.build_ack("CTRL001", self.original_msg)
        self.assertIsNotNone(ack)

    def test_build_ack_has_aa_code(self) -> None:
        ack = self.builder.build_ack("CTRL001", self.original_msg)
        msa = ack.msa
        self.assertEqual(msa.msa_1.value, Hl7Constants.ACK_CODE_ACCEPT)

    def test_build_ack_echoes_control_id(self) -> None:
        ack = self.builder.build_ack("CTRL001", self.original_msg)
        self.assertEqual(ack.msa.msa_2.value, "CTRL001")

    def test_build_ack_swaps_sending_and_receiving(self) -> None:
        ack = self.builder.build_ack("CTRL001", self.original_msg)
        # Sending app of ACK = receiving app of original
        self.assertEqual(ack.msh.msh_3.value, "RECEIVER")
        # Receiving app of ACK = sending app of original
        self.assertEqual(ack.msh.msh_5.value, "SENDER")

    def test_build_ack_to_mllp_has_mllp_framing(self) -> None:
        ack = self.builder.build_ack("CTRL001", self.original_msg)
        mllp = ack.to_mllp()
        self.assertTrue(mllp.startswith("\x0b"))
        self.assertTrue(mllp.endswith("\x1c\r"))

    def test_build_ack_message_type_is_ack(self) -> None:
        ack = self.builder.build_ack("CTRL001", self.original_msg)
        self.assertEqual(ack.msh.msh_9.message_code.value, "ACK")


if __name__ == "__main__":
    unittest.main()
