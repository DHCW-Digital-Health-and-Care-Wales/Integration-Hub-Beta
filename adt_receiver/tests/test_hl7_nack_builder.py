import unittest

from adt_receiver.hl7_constant import Hl7Constants
from adt_receiver.hl7_nack_builder import HL7NackBuilder

VALID_ADT_MESSAGE = (
    "MSH|^~\\&|SENDER|FAC_SEND|RECEIVER|FAC_RECV|20250506120000||ADT^A01^ADT_A01|CTRL001|P|2.5\r"
    "PID|1||12345^^^Hospital^MR||Smith^John\r"
)

UNPARSEABLE_MESSAGE = "NOT A VALID HL7 MESSAGE"


class TestHL7NackBuilder(unittest.TestCase):

    def setUp(self) -> None:
        self.builder = HL7NackBuilder()

    def test_build_nack_returns_message(self) -> None:
        nack = self.builder.build_nack(VALID_ADT_MESSAGE)
        self.assertIsNotNone(nack)

    def test_build_nack_has_ae_code(self) -> None:
        nack = self.builder.build_nack(VALID_ADT_MESSAGE)
        self.assertEqual(nack.msa.msa_1.value, Hl7Constants.NACK_CODE_ERROR)

    def test_build_nack_echoes_control_id(self) -> None:
        nack = self.builder.build_nack(VALID_ADT_MESSAGE)
        self.assertEqual(nack.msa.msa_2.value, "CTRL001")

    def test_build_nack_swaps_sending_and_receiving(self) -> None:
        nack = self.builder.build_nack(VALID_ADT_MESSAGE)
        self.assertEqual(nack.msh.msh_3.value, "RECEIVER")
        self.assertEqual(nack.msh.msh_5.value, "SENDER")

    def test_build_nack_to_mllp_has_mllp_framing(self) -> None:
        nack = self.builder.build_nack(VALID_ADT_MESSAGE)
        mllp = nack.to_mllp()
        self.assertTrue(mllp.startswith("\x0b"))
        self.assertTrue(mllp.endswith("\x1c\r"))

    def test_build_nack_with_unparseable_message_uses_fallback(self) -> None:
        nack = self.builder.build_nack(UNPARSEABLE_MESSAGE)
        self.assertIsNotNone(nack)
        self.assertEqual(nack.msa.msa_1.value, Hl7Constants.NACK_CODE_ERROR)
        self.assertEqual(nack.msa.msa_2.value, "UNKNOWN")

    def test_build_nack_message_type_is_ack(self) -> None:
        nack = self.builder.build_nack(VALID_ADT_MESSAGE)
        self.assertEqual(nack.msh.msh_9.message_code.value, "ACK")


if __name__ == "__main__":
    unittest.main()
