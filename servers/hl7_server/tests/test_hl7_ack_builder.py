import unittest

from hl7apy.core import Message
from hl7apy.parser import parse_message

from hl7_server.hl7_ack_builder import HL7AckBuilder

MESSAGE_CONTROL_ID = "202505052323364444"


def _inbound_message(processing_id: str) -> str:
    """Build a minimal inbound ADT^A31 with the given MSH-11 processing ID."""
    return (
        f"MSH|^~\\&|252|252|100|100|20250505232332||ADT^A31^ADT_A05|{MESSAGE_CONTROL_ID}|"
        f"{processing_id}|2.5\r"
        "PID|1||123456^^^Hospital^MR||Doe^John\r"
    )


class TestHL7AckBuilder(unittest.TestCase):
    def setUp(self) -> None:
        self.builder = HL7AckBuilder()

    def _build(self, processing_id: str) -> Message:
        original_msg = parse_message(_inbound_message(processing_id), find_groups=False)
        return self.builder.build_ack(MESSAGE_CONTROL_ID, original_msg)

    def test_processing_id_copied_from_test_message(self) -> None:
        # A test message must not be acknowledged as production (HL7 v2.5 section 2.9.2.2).
        ack = self._build("T")

        self.assertEqual("T", ack.msh.msh_11.value)

    def test_processing_id_copied_from_production_message(self) -> None:
        ack = self._build("P")

        self.assertEqual("P", ack.msh.msh_11.value)

    def test_processing_id_defaults_when_inbound_field_missing(self) -> None:
        # MSH-11 is required in the ACK, so an absent inbound value must still yield a valid message.
        ack = self._build("")

        self.assertEqual("P", ack.msh.msh_11.value)

    def test_ack_header_and_msa_built_correctly(self) -> None:
        ack = self._build("T")

        # Sending and receiving application/facility are swapped relative to the inbound message.
        self.assertEqual("100", ack.msh.msh_3.value)
        self.assertEqual("100", ack.msh.msh_4.value)
        self.assertEqual("252", ack.msh.msh_5.value)
        self.assertEqual("252", ack.msh.msh_6.value)
        self.assertEqual("ACK^A31^ACK", ack.msh.msh_9.value)
        self.assertEqual("2.5", ack.msh.msh_12.value)
        self.assertEqual("AA", ack.msa.msa_1.value)
        self.assertEqual(MESSAGE_CONTROL_ID, ack.msa.msa_2.value)


class TestHL7AckBuilderNacks(unittest.TestCase):
    def setUp(self) -> None:
        self.builder = HL7AckBuilder()

    def _parsed_original(self, processing_id: str = "P") -> Message:
        return parse_message(_inbound_message(processing_id), find_groups=False)

    def test_build_nack_sets_reject_code_and_reason(self) -> None:
        original_msg = self._parsed_original()
        nack = self.builder.build_nack(MESSAGE_CONTROL_ID, original_msg, "AR", "Message has wrong version")

        self.assertEqual("AR", nack.msa.msa_1.value)
        self.assertEqual(MESSAGE_CONTROL_ID, nack.msa.msa_2.value)
        self.assertEqual("Message has wrong version", nack.msa.msa_3.value)
        # Swapped, same as build_ack.
        self.assertEqual("100", nack.msh.msh_3.value)
        self.assertEqual("252", nack.msh.msh_5.value)

    def test_build_nack_sets_error_code(self) -> None:
        original_msg = self._parsed_original()
        nack = self.builder.build_nack(MESSAGE_CONTROL_ID, original_msg, "AE", "Unexpected failure")

        self.assertEqual("AE", nack.msa.msa_1.value)

    def test_build_nack_sanitizes_and_truncates_reason(self) -> None:
        original_msg = self._parsed_original()
        long_reason = ("bad value spans lines " * 20) + "\r\nend"

        nack = self.builder.build_nack(MESSAGE_CONTROL_ID, original_msg, "AR", long_reason)

        reason_text = nack.msa.msa_3.to_er7()
        self.assertNotIn("\r", reason_text)
        self.assertNotIn("\n", reason_text)

    def test_sanitize_reason_strips_line_breaks_and_truncates(self) -> None:
        long_reason = ("x" * 300) + "\r\n" + "y" * 50

        sanitized = HL7AckBuilder._sanitize_reason(long_reason)

        self.assertNotIn("\r", sanitized)
        self.assertNotIn("\n", sanitized)
        self.assertLessEqual(len(sanitized), 199)

    def test_build_generic_nack_uses_generated_control_id_when_none_given(self) -> None:
        nack = self.builder.build_generic_nack("Unable to parse message")

        self.assertEqual("AE", nack.msa.msa_1.value)
        self.assertTrue(nack.msh.msh_10.value)
        self.assertEqual(nack.msh.msh_10.value, nack.msa.msa_2.value)
        self.assertLessEqual(len(nack.msh.msh_10.value), 20)

    def test_build_generic_nack_uses_given_control_id(self) -> None:
        nack = self.builder.build_generic_nack("Unable to parse message", message_control_id="ABC123")

        self.assertEqual("ABC123", nack.msh.msh_10.value)
        self.assertEqual("ABC123", nack.msa.msa_2.value)

    def test_build_generic_nack_is_mllp_framed(self) -> None:
        nack = self.builder.build_generic_nack("Unable to parse message")

        framed = nack.to_mllp()
        self.assertTrue(framed.startswith("\x0b"))
        self.assertTrue(framed.endswith("\x1c\r"))


if __name__ == "__main__":
    unittest.main()
