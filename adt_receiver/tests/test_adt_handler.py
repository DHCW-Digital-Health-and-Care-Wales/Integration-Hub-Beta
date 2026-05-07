import unittest
from unittest.mock import ANY, MagicMock, patch

from adt_receiver.adt_handler import AdtHandler
from adt_receiver.exceptions.validation_exception import ValidationException

VALID_ADT_A01 = (
    "MSH|^~\\&|SENDER|FACILITY|RECEIVER|DEST|20250506120000||ADT^A01^ADT_A01|MSG001|P|2.5\r"
    "PID|1||12345^^^Hospital^MR||Smith^John\r"
)

VALID_ADT_A28 = (
    "MSH|^~\\&|SENDER|FACILITY|RECEIVER|DEST|20250506120000||ADT^A28^ADT_A05|MSG002|P|2.5\r"
    "PID|1||67890^^^Hospital^MR||Doe^Jane\r"
)

ACK_BUILDER_ATTRIBUTE = "adt_receiver.adt_handler.HL7AckBuilder"


class TestAdtHandler(unittest.TestCase):

    def setUp(self) -> None:
        self.mock_sender = MagicMock()
        self.mock_event_logger = MagicMock()
        self.mock_metric_sender = MagicMock()
        self.mock_validator = MagicMock()
        self.handler = AdtHandler(
            VALID_ADT_A01,
            self.mock_sender,
            self.mock_event_logger,
            self.mock_metric_sender,
            self.mock_validator,
        )

    def test_valid_adt_a01_returns_ack(self) -> None:
        with patch(ACK_BUILDER_ATTRIBUTE) as mock_builder:
            mock_instance = mock_builder.return_value
            mock_ack = MagicMock()
            mock_ack.to_mllp.return_value = "\x0bACK_CONTENT\x1c\r"
            mock_instance.build_ack.return_value = mock_ack

            result = self.handler.reply()

            self.assertIn("ACK_CONTENT", result)

    def test_valid_adt_message_sends_to_service_bus(self) -> None:
        with patch(ACK_BUILDER_ATTRIBUTE):
            self.handler.reply()

        self.mock_sender.send_text_message.assert_called_once_with(VALID_ADT_A01, None)

    def test_metric_sent_on_message_received(self) -> None:
        with patch(ACK_BUILDER_ATTRIBUTE):
            self.handler.reply()

        self.mock_metric_sender.send_message_received_metric.assert_called_once()

    def test_validation_exception_raises_and_logs(self) -> None:
        exc = ValidationException("Invalid ADT message")
        self.mock_validator.validate.side_effect = exc

        with self.assertRaises(ValidationException):
            self.handler.reply()

        self.mock_event_logger.log_message_failed.assert_called_once()
        self.mock_sender.send_text_message.assert_not_called()

    def test_ack_builder_called_with_correct_control_id(self) -> None:
        with patch(ACK_BUILDER_ATTRIBUTE) as mock_builder:
            mock_instance = mock_builder.return_value
            mock_ack = MagicMock()
            mock_ack.to_mllp.return_value = "\x0bACK\x1c\r"
            mock_instance.build_ack.return_value = mock_ack

            self.handler.reply()

            mock_instance.build_ack.assert_called_once_with("MSG001", ANY)

    def test_service_bus_failure_raises_and_logs(self) -> None:
        self.mock_sender.send_text_message.side_effect = RuntimeError("Service Bus unavailable")

        with self.assertRaises(RuntimeError):
            self.handler.reply()

        self.mock_event_logger.log_message_failed.assert_called_once()

    def test_different_adt_types_are_processed(self) -> None:
        handler_a28 = AdtHandler(
            VALID_ADT_A28,
            self.mock_sender,
            self.mock_event_logger,
            self.mock_metric_sender,
            self.mock_validator,
        )
        with patch(ACK_BUILDER_ATTRIBUTE) as mock_builder:
            mock_instance = mock_builder.return_value
            mock_ack = MagicMock()
            mock_ack.to_mllp.return_value = "\x0bACK\x1c\r"
            mock_instance.build_ack.return_value = mock_ack

            result = handler_a28.reply()

        self.assertIsNotNone(result)

    def test_event_logger_called_on_message_received(self) -> None:
        with patch(ACK_BUILDER_ATTRIBUTE):
            self.handler.reply()

        self.mock_event_logger.log_message_received.assert_called_once_with(VALID_ADT_A01)

    def test_event_logger_called_on_success(self) -> None:
        with patch(ACK_BUILDER_ATTRIBUTE):
            self.handler.reply()

        self.mock_event_logger.log_message_processed.assert_called_once()


if __name__ == "__main__":
    unittest.main()
