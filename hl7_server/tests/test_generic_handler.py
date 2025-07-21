import unittest
from unittest.mock import ANY, MagicMock, patch

from hl7_server.generic_handler import GenericHandler
from hl7_server.hl7_validator import ValidationException

# Sample valid HL7 message (pipe & hat, type A28)
VALID_A28_MESSAGE = """MSH|^~\&|252|252|100|100|20250505232332||ADT_ALL|202505052323364444|P|2.5|||||||||||1
EVN|A28|20250505232332
PID|1|123456|||Hospital^MR||||Doe^John^^^L
PV1|1|I
MRG|123456|||Hospital^MR"""

ACK_BUILDER_ATTRIBUTE = "hl7_server.generic_handler.HL7AckBuilder"


class TestGenericHandler(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_sender = MagicMock()
        self.mock_audit_client = MagicMock()
        self.validator = MagicMock()
        self.handler = GenericHandler(VALID_A28_MESSAGE, self.mock_sender, self.mock_audit_client, self.validator)

    def test_valid_a28_message_returns_ack(self) -> None:
        with patch(ACK_BUILDER_ATTRIBUTE) as mock_builder:
            mock_instance = mock_builder.return_value
            mock_ack_message = MagicMock()
            mock_ack_message.to_mllp.return_value = "\x0bACK_CONTENT\x1c\r"
            mock_instance.build_ack.return_value = mock_ack_message
            result = self.handler.reply()

            mock_instance.build_ack.assert_called_once()
            self.assertIn("ACK_CONTENT", result)

    def test_ack_message_created_correctly(self) -> None:
        with patch(ACK_BUILDER_ATTRIBUTE) as MockAckBuilder:
            mock_builder_instance = MockAckBuilder.return_value

            # Mock the Message-like object returned from build_ack
            mock_ack_message = MagicMock()
            mock_ack_message.to_mllp.return_value = (
                "\x0bMSH|^~\\&|100|100|252|252|202405280830||ACK^A28^ACK|123456|P|2.5\rMSA|AA|123456\r\x1c\r"
            )
            mock_builder_instance.build_ack.return_value = mock_ack_message

            ack_response = self.handler.reply()

            self.assertIn("MSA|AA|123456", ack_response)
            self.assertIn("ACK^A28^ACK", ack_response)
            self.assertTrue(ack_response.startswith("\x0b"))
            self.assertTrue(ack_response.endswith("\x1c\r"))

            mock_builder_instance.build_ack.assert_called_once_with("202505052323364444", ANY)
            mock_ack_message.to_mllp.assert_called_once()

    @patch("hl7_server.generic_handler.logger")
    def test_validation_exception(self, mock_logger: MagicMock) -> None:
        exception = ValidationException("Invalid sending app id")
        message = "MSH|^~\\&|100|100|100|252|202405280830||ACK^A28^ACK|123456|P|2.5\r"

        validator = MagicMock()
        validator.validate = MagicMock(side_effect=exception)
        handler = GenericHandler(message, self.mock_sender, self.mock_audit_client, validator)

        with self.assertRaises(ValidationException):
            handler.reply()

        mock_logger.error.assert_called_once_with(f"HL7 validation error: {exception}")
        self.mock_audit_client.log_message_failed.assert_called_once_with(message, f"HL7 validation error: {exception}")

    def test_message_sent_to_service_bus(self) -> None:
        self.handler.reply()

        self.mock_sender.send_text_message.assert_called_once_with(VALID_A28_MESSAGE)


if __name__ == "__main__":
    unittest.main()
