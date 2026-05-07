import unittest
from unittest.mock import MagicMock, patch

from hl7apy.mllp import UnsupportedMessageType

from adt_receiver.error_handler import ErrorHandler

VALID_ADT_MESSAGE = (
    "MSH|^~\\&|SENDER|FAC_SEND|RECEIVER|FAC_RECV|20250506120000||ADT^A01^ADT_A01|CTRL001|P|2.5\r"
    "PID|1||12345^^^Hospital^MR||Smith^John\r"
)

NACK_BUILDER_ATTRIBUTE = "adt_receiver.error_handler.HL7NackBuilder"


class TestErrorHandler(unittest.TestCase):

    def setUp(self) -> None:
        self.mock_event_logger = MagicMock()

    def test_unsupported_message_type_returns_nack(self) -> None:
        exc = UnsupportedMessageType("ORU^R01")
        handler = ErrorHandler(exc, VALID_ADT_MESSAGE, self.mock_event_logger)

        with patch(NACK_BUILDER_ATTRIBUTE) as mock_builder:
            mock_instance = mock_builder.return_value
            mock_nack = MagicMock()
            mock_nack.to_mllp.return_value = "\x0bNACK_CONTENT\x1c\r"
            mock_instance.build_nack.return_value = mock_nack

            result = handler.reply()

        self.assertIn("NACK_CONTENT", result)
        self.mock_event_logger.log_message_failed.assert_called_once()

    def test_invalid_message_returns_nack(self) -> None:
        exc = ValueError("Failed to parse HL7")
        handler = ErrorHandler(exc, VALID_ADT_MESSAGE, self.mock_event_logger)

        with patch(NACK_BUILDER_ATTRIBUTE) as mock_builder:
            mock_instance = mock_builder.return_value
            mock_nack = MagicMock()
            mock_nack.to_mllp.return_value = "\x0bNACK_CONTENT\x1c\r"
            mock_instance.build_nack.return_value = mock_nack

            result = handler.reply()

        self.assertIn("NACK_CONTENT", result)

    def test_error_handler_logs_unsupported_type(self) -> None:
        exc = UnsupportedMessageType("ORU^R01")
        handler = ErrorHandler(exc, VALID_ADT_MESSAGE, self.mock_event_logger)

        with patch(NACK_BUILDER_ATTRIBUTE) as mock_builder:
            mock_nack = MagicMock()
            mock_nack.to_mllp.return_value = "\x0bNACK\x1c\r"
            mock_builder.return_value.build_nack.return_value = mock_nack
            handler.reply()

        call_args = self.mock_event_logger.log_message_failed.call_args
        self.assertIn("Unsupported", call_args[0][1])

    def test_error_handler_logs_invalid_message(self) -> None:
        exc = RuntimeError("Parse error")
        handler = ErrorHandler(exc, VALID_ADT_MESSAGE, self.mock_event_logger)

        with patch(NACK_BUILDER_ATTRIBUTE) as mock_builder:
            mock_nack = MagicMock()
            mock_nack.to_mllp.return_value = "\x0bNACK\x1c\r"
            mock_builder.return_value.build_nack.return_value = mock_nack
            handler.reply()

        call_args = self.mock_event_logger.log_message_failed.call_args
        self.assertIn("Invalid", call_args[0][1])


if __name__ == "__main__":
    unittest.main()
