import unittest
from unittest.mock import ANY, MagicMock, patch

from hl7_server.chemocare_handler import ChemocareHandler

# Sample valid Chemocare HL7 v2.4 A31 message from South_East_Wales_Chemocare
VALID_CHEMOCARE_A31_MESSAGE = (
    "MSH|^~\\&|245|245|100|100|2025-05-05 23:23:32||ADT^A31^ADT_A05|202505052323364444|P|2.4|||||GBR||EN\r"
    "PID|1||123456^^^Hospital^MR||Doe^John\r"
)

# Sample valid Chemocare HL7 v2.4 A28 message from BU_CHEMOCARE_TO_MPI
VALID_CHEMOCARE_A28_MESSAGE = (
    "MSH|^~\\&|212|212|100|100|2025-05-05 23:23:32||ADT^A28^ADT_A05|202505052323364445|P|2.4|||||GBR||EN\r"
    "PID|1||123456^^^Hospital^MR||Doe^John\r"
)

INVALID_VERSION_MESSAGE = (
    "MSH|^~\\&|245|245|100|100|2025-05-05 23:23:32||ADT^A31^ADT_A05|202505052323364448|P|2.5|||||GBR||EN\r"
    "PID|1||123456^^^Hospital^MR||Doe^John\r"
)

ACK_BUILDER_ATTRIBUTE = "hl7_server.base_handler.HL7AckBuilder"


class TestChemocareHandler(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_sender = MagicMock()
        self.mock_audit_client = MagicMock()
        self.mock_validator = MagicMock()

    def test_valid_chemocare_messages_return_success_ack(self) -> None:
        test_cases = [
            ("A31", VALID_CHEMOCARE_A31_MESSAGE, "202505052323364444"),
            ("A28", VALID_CHEMOCARE_A28_MESSAGE, "202505052323364445"),
        ]

        for message_type, message, expected_control_id in test_cases:
            with self.subTest(message_type=message_type, control_id=expected_control_id):
                handler = ChemocareHandler(message, self.mock_sender, self.mock_audit_client, self.mock_validator)

                with patch(ACK_BUILDER_ATTRIBUTE) as MockAckBuilder:
                    mock_builder_instance = MockAckBuilder.return_value
                    mock_ack_message = MagicMock()
                    mock_ack_message.to_mllp.return_value = "\x0bACK_SUCCESS_CONTENT\x1c\r"
                    mock_builder_instance.build_ack.return_value = mock_ack_message

                    result = handler.reply()

                    mock_builder_instance.build_ack.assert_called_once_with(expected_control_id, ANY, None, None)
                    self.assertIn("ACK_SUCCESS_CONTENT", result)
                    self.mock_sender.send_text_message.assert_called_once_with(message)
                    self.mock_audit_client.log_message_received.assert_called_once()
                    self.mock_audit_client.log_validation_result.assert_called_once()
                    self.mock_audit_client.log_message_processed.assert_called_once()

                self.mock_sender.reset_mock()
                self.mock_audit_client.reset_mock()

    @patch("hl7_server.chemocare_handler.logger")
    def test_chemocare_messages_processed_without_validation(self, mock_logger: MagicMock) -> None:
        """Test that Chemocare messages are processed without any validation"""
        handler = ChemocareHandler(
            INVALID_VERSION_MESSAGE, self.mock_sender, self.mock_audit_client, self.mock_validator
        )

        with patch(ACK_BUILDER_ATTRIBUTE) as MockAckBuilder:
            mock_builder_instance = MockAckBuilder.return_value
            mock_ack_message = MagicMock()
            mock_ack_message.to_mllp.return_value = "\x0bACK_CONTENT\x1c\r"
            mock_builder_instance.build_ack.return_value = mock_ack_message

            # Should not raise any validation errors
            result = handler.reply()

            self.assertIn("ACK_CONTENT", result)
            self.mock_sender.send_text_message.assert_called_once_with(INVALID_VERSION_MESSAGE)
            self.mock_audit_client.log_message_received.assert_called_once()
            self.mock_audit_client.log_validation_result.assert_called_once()
            self.mock_audit_client.log_message_processed.assert_called_once()

    @patch("hl7_server.chemocare_handler.logger")
    def test_successful_message_processing_audit_trail(self, mock_logger: MagicMock) -> None:
        handler = ChemocareHandler(
            VALID_CHEMOCARE_A31_MESSAGE, self.mock_sender, self.mock_audit_client, self.mock_validator
        )

        with patch(ACK_BUILDER_ATTRIBUTE) as MockAckBuilder:
            mock_builder_instance = MockAckBuilder.return_value
            mock_ack_message = MagicMock()
            mock_ack_message.to_mllp.return_value = "\x0bACK_CONTENT\x1c\r"
            mock_builder_instance.build_ack.return_value = mock_ack_message

            handler.reply()

            self.mock_audit_client.log_message_received.assert_called_once_with(
                VALID_CHEMOCARE_A31_MESSAGE, "Chemocare message received"
            )

            validation_call = self.mock_audit_client.log_validation_result.call_args
            self.assertIn("processed without validation", validation_call[0][1])

            processing_call = self.mock_audit_client.log_message_processed.call_args
            self.assertEqual(processing_call[0][1], "Successfully processed Chemocare message")

    @patch("hl7_server.chemocare_handler.logger")
    def test_service_bus_failure_handling(self, mock_logger: MagicMock) -> None:
        handler = ChemocareHandler(
            VALID_CHEMOCARE_A31_MESSAGE, self.mock_sender, self.mock_audit_client, self.mock_validator
        )
        self.mock_sender.send_text_message.side_effect = Exception("Service Bus connection failed")

        with self.assertRaises(Exception):
            handler.reply()

        self.mock_sender.send_text_message.assert_called_once_with(VALID_CHEMOCARE_A31_MESSAGE)


if __name__ == "__main__":
    unittest.main()
