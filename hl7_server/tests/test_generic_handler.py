import unittest
from unittest.mock import ANY, MagicMock, patch

from hl7_server.generic_handler import GenericHandler
from hl7_server.hl7_constant import Hl7Constants
from hl7_server.hl7_validator import ValidationException

# Sample valid HL7 message (pipe & hat, type A28)
PHW_A28_MESSAGE = (
    "MSH|^~\\&|252|252|100|100|2025-05-05 23:23:32||ADT^A28^ADT_A05|202505052323364444|P|2.5|||||GBR||EN\r"
    "PID|1||123456^^^Hospital^MR||Doe^John\r"
)

# Sample valid Chemocare HL7 v2.4 A31 message
CHEMOCARE_A31_MESSAGE = (
    "MSH|^~\\&|245|245|100|100|2025-05-05 23:23:32||ADT^A31^ADT_A05|202505052323364444|P|2.4|||||GBR||EN\r"
    "PID|1||123456^^^Hospital^MR||Doe^John\r"
)

# Sample unknown authority code message
OTHER_AUTHORITY_A31_MESSAGE = (
    "MSH|^~\\&|999|999|100|100|2025-05-05 23:23:32||ADT^A31^ADT_A05|202505052323364444|P|2.5|||||GBR||EN\r"
    "PID|1||123456^^^Hospital^MR||Doe^John\r"
)


ACK_BUILDER_ATTRIBUTE = "hl7_server.generic_handler.HL7AckBuilder"
CHEMOCARE_HANDLER_ATTRIBUTE = "hl7_server.chemocare_handler.ChemocareHandler"


class TestGenericHandler(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_sender = MagicMock()
        self.mock_audit_client = MagicMock()
        self.validator = MagicMock()

    def test_PHW_A28_MESSAGE_returns_ack(self) -> None:
        handler = GenericHandler(PHW_A28_MESSAGE, self.mock_sender, self.mock_audit_client, self.validator)

        with patch(ACK_BUILDER_ATTRIBUTE) as mock_builder:
            with patch(CHEMOCARE_HANDLER_ATTRIBUTE) as mock_chemocare_handler_class:
                mock_builder_instance = mock_builder.return_value
                mock_ack_message = MagicMock()
                mock_ack_message.to_mllp.return_value = "\x0bPHW_ACK_CONTENT\x1c\r"
                mock_builder_instance.build_ack.return_value = mock_ack_message

                result = handler.reply()

                mock_chemocare_handler_class.assert_not_called()
                self.validator.validate.assert_called_once()
                self.mock_sender.send_text_message.assert_called_once_with(PHW_A28_MESSAGE)
                mock_builder_instance.build_ack.assert_called_once()
                self.assertIn("PHW_ACK_CONTENT", result)

    def test_ack_message_created_correctly(self) -> None:
        handler = GenericHandler(PHW_A28_MESSAGE, self.mock_sender, self.mock_audit_client, self.validator)

        with patch(ACK_BUILDER_ATTRIBUTE) as MockAckBuilder:
            mock_builder_instance = MockAckBuilder.return_value

            # Mock the Message-like object returned from build_ack
            mock_ack_message = MagicMock()
            mock_ack_message.to_mllp.return_value = (
                "\x0bMSH|^~\\&|100|100|252|252|202405280830||ACK^A28^ACK|123456|P|2.5\rMSA|AA|123456\r\x1c\r"
            )
            mock_builder_instance.build_ack.return_value = mock_ack_message

            ack_response = handler.reply()

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
        handler = GenericHandler(PHW_A28_MESSAGE, self.mock_sender, self.mock_audit_client, self.validator)

        handler.reply()

        self.mock_sender.send_text_message.assert_called_once_with(PHW_A28_MESSAGE)

    def test_processes_other_authority_message_normally(self) -> None:
        handler = GenericHandler(OTHER_AUTHORITY_A31_MESSAGE, self.mock_sender, self.mock_audit_client, self.validator)

        with patch(ACK_BUILDER_ATTRIBUTE) as mock_ack_builder:
            with patch(CHEMOCARE_HANDLER_ATTRIBUTE) as mock_chemocare_handler_class:
                mock_builder_instance = mock_ack_builder.return_value
                mock_ack_message = MagicMock()
                mock_ack_message.to_mllp.return_value = "\x0bOTHER_ACK_CONTENT\x1c\r"
                mock_builder_instance.build_ack.return_value = mock_ack_message

                result = handler.reply()

                mock_chemocare_handler_class.assert_not_called()
                self.validator.validate.assert_called_once()
                self.mock_sender.send_text_message.assert_called_once_with(OTHER_AUTHORITY_A31_MESSAGE)
                mock_builder_instance.build_ack.assert_called_once()
                self.assertIn("OTHER_ACK_CONTENT", result)

    def test_delegates_chemocare_message_to_chemocare_handler(self) -> None:
        handler = GenericHandler(CHEMOCARE_A31_MESSAGE, self.mock_sender, self.mock_audit_client, self.validator)

        with patch(CHEMOCARE_HANDLER_ATTRIBUTE) as mock_chemocare_handler_class:
            mock_chemocare_instance = mock_chemocare_handler_class.return_value
            mock_chemocare_instance.reply.return_value = "\x0bCHEMOCARE_ACK_RESPONSE\x1c\r"

            result = handler.reply()

            mock_chemocare_handler_class.assert_called_once_with(
                CHEMOCARE_A31_MESSAGE, self.mock_sender, self.mock_audit_client, self.validator
            )
            mock_chemocare_instance.reply.assert_called_once()
            self.assertIn("CHEMOCARE_ACK_RESPONSE", result)

    def test_chemocare_authority_codes_handled_by_chemocare_handler(self) -> None:
        for authority_code in Hl7Constants.CHEMOCARE_AUTHORITY_CODES.keys():
            test_message = (
                f"MSH|^~\\&|{authority_code}|{authority_code}|100|100|2025-05-05 23:23:32||ADT^A31^ADT_A05|12345|P|2.4|||||GBR||EN\r"
                "PID|1||123456^^^Hospital^MR||Doe^John\r"
            )

            handler = GenericHandler(test_message, self.mock_sender, self.mock_audit_client, self.validator)

            with patch(CHEMOCARE_HANDLER_ATTRIBUTE) as mock_chemocare_handler_class:
                mock_chemocare_instance = mock_chemocare_handler_class.return_value
                mock_chemocare_instance.reply.return_value = "\x0bTEST_ACK\x1c\r"

                handler.reply()

                mock_chemocare_handler_class.assert_called_once()
                mock_chemocare_instance.reply.assert_called_once()
                mock_chemocare_handler_class.reset_mock()


if __name__ == "__main__":
    unittest.main()
