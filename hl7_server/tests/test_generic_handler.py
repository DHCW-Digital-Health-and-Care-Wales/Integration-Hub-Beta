import unittest
from unittest.mock import patch, MagicMock
from hl7_server.dhcw_nhs_wale.generic_handler import GenericHandler, InvalidHL7FormatException

# Sample valid HL7 message (pipe & hat, type A28)
VALID_A28_MESSAGE = (
    "MSH|^~\&|252|252|100|100|2025-05-05 23:23:32||ADT^A31^ADT_A05|202505052323364444|P|2.5|||||GBR||EN\r"
    "PID|1||123456^^^Hospital^MR||Doe^John\r"
)

# Invalid message: wrong format
INVALID_FORMAT_MESSAGE = (
    "BAD_HEADER|NoHat|App|Fac|App|Fac|20240528||ORM^O01|1234|P|2.3"
)

# Unsupported message type
UNSUPPORTED_MESSAGE = (
    "MSH|^~\&|252|252|100|100|2025-05-05 23:23:32||ORM^O01^ORM_O01|123456|P|2.3\r"
    "PID|1||123456^^^Hospital^MR||Smith^Jane\r"
)


class TestGenericHandler(unittest.TestCase):


    def test_valid_a28_message_returns_ack(self):
        self.handler = GenericHandler(VALID_A28_MESSAGE)

        with patch('hl7_server.dhcw_nhs_wale.generic_handler.HL7AckBuilder') as mock_builder:
            mock_instance = mock_builder.return_value
            mock_instance.build_ack.return_value.to_er7.return_value = "ACK_CONTENT"
            mock_instance.to_mllp.return_value = "\x0bACK_CONTENT\x1c\r"

            result = self.handler.reply()

            mock_instance.build_ack.assert_called_once()
            self.assertIn("ACK_CONTENT", result)

    def test_invalid_format_raises_exception(self):
        self.handler = GenericHandler(INVALID_FORMAT_MESSAGE)

        with self.assertRaises(InvalidHL7FormatException):
            self.handler.reply()

    def test_unsupported_message_type_raises_exception(self):
        self.handler = GenericHandler(UNSUPPORTED_MESSAGE)

        with self.assertRaises(Exception) as context:
            self.handler.reply()
        self.assertIn("Unsupported message type: ORM^O01^ORM_O01", str(context.exception))

    def test_ack_message_created_correctly(self):
        handler = GenericHandler(VALID_A28_MESSAGE)

        # Mock HL7AckBuilder methods
        with patch('hl7_server.dhcw_nhs_wale.generic_handler.HL7AckBuilder') as MockAckBuilder:
            mock_builder_instance = MockAckBuilder.return_value

            # Simulate build_ack returning a Message-like object
            mock_ack_message = MagicMock()
            mock_ack_message.to_er7.return_value = (
                "MSH|^~\\&|100|100|252|252|202405280830||ACK^A28^ACK|123456|P|2.5\r"
                "MSA|AA|123456\r"
            )

            mock_builder_instance.build_ack.return_value = mock_ack_message
            mock_builder_instance.to_mllp.return_value = f"\x0b{mock_ack_message.to_er7()}\x1c\r"

            ack_response = handler.reply()

            # Verify that the ACK message contains correct control ID and ACK code
            self.assertIn("MSA|AA|123456", ack_response)
            self.assertIn("ACK^A28^ACK", ack_response)
            self.assertTrue(ack_response.startswith("\x0b"))
            self.assertTrue(ack_response.endswith("\x1c\r"))

            mock_builder_instance.build_ack.assert_called_once_with("202505052323364444")
            mock_builder_instance.to_mllp.assert_called_once_with(mock_ack_message)


if __name__ == '__main__':
    unittest.main()
