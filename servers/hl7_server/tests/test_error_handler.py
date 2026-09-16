import unittest
from unittest.mock import MagicMock, patch

from hl7_validation import XmlValidationError
from hl7apy.mllp import InvalidHL7Message, UnsupportedMessageType

from hl7_server.error_handler import ErrorHandler
from hl7_server.exceptions.validation_exception import ValidationException

VALID_MESSAGE = (
    r"MSH|^~\&|GHH_ADT|RECEIVING_APP|SENDING_APP|SENDING_FAC|20080115153000||ADT^A31^ADT_A05|"
    r"0123456789|P|2.5"
)


class TestErrorHandler(unittest.TestCase):
    @patch("hl7_server.error_handler.logger")
    def test_reply_with_unsupported_message_type_returns_ae_nack(self, mock_logger: MagicMock) -> None:
        exception = UnsupportedMessageType("Unsupported type")
        mock_event_logger = MagicMock()

        handler = ErrorHandler(exception, VALID_MESSAGE, mock_event_logger)
        reply = handler.reply()

        mock_logger.error.assert_called_once_with(f"Unsupported Message Type: {exception}")
        mock_event_logger.log_message_failed.assert_called_once_with(
            VALID_MESSAGE, f"Unsupported Message Type: {exception}", "Unsupported message type"
        )
        self.assertIn("MSA|AE|0123456789", reply)

    @patch("hl7_server.error_handler.logger")
    def test_reply_with_invalid_hl7_message_exception_returns_ae_nack(self, mock_logger: MagicMock) -> None:
        exception = InvalidHL7Message("invalid message")
        invalid_message = "<hello>"
        mock_event_logger = MagicMock()

        handler = ErrorHandler(exception, invalid_message, mock_event_logger)
        reply = handler.reply()

        mock_logger.error.assert_called_once_with(f"Invalid HL7 Message: {exception}")
        mock_event_logger.log_message_failed.assert_called_once_with(
            invalid_message, f"Invalid HL7 Message: {exception}", "Invalid HL7 message format"
        )
        # No original message could be parsed, so a generic NACK (generated control ID) is used.
        self.assertIn("MSA|AE|", reply)

    @patch("hl7_server.error_handler.logger")
    def test_reply_with_validation_exception_returns_ar_nack(self, mock_logger: MagicMock) -> None:
        exception = ValidationException("Message has wrong version")
        mock_event_logger = MagicMock()

        handler = ErrorHandler(exception, VALID_MESSAGE, mock_event_logger)
        reply = handler.reply()

        mock_logger.error.assert_called_once_with(f"HL7 validation error: {exception}")
        mock_event_logger.log_message_failed.assert_called_once_with(
            VALID_MESSAGE, f"HL7 validation error: {exception}", "HL7 validation failed"
        )
        self.assertIn("MSA|AR|0123456789", reply)

    @patch("hl7_server.error_handler.logger")
    def test_reply_with_xml_validation_error_returns_ar_nack(self, mock_logger: MagicMock) -> None:
        exception = XmlValidationError("Schema validation failed")
        mock_event_logger = MagicMock()

        handler = ErrorHandler(exception, VALID_MESSAGE, mock_event_logger)
        reply = handler.reply()

        self.assertIn("MSA|AR|0123456789", reply)

    @patch("hl7_server.error_handler.logger")
    def test_reply_with_unexpected_exception_returns_ae_nack(self, mock_logger: MagicMock) -> None:
        exception = RuntimeError("Service Bus send failed")
        mock_event_logger = MagicMock()

        handler = ErrorHandler(exception, VALID_MESSAGE, mock_event_logger)
        reply = handler.reply()

        mock_logger.error.assert_called_once_with(f"Unexpected error while processing message: {exception}")
        mock_event_logger.log_message_failed.assert_called_once_with(
            VALID_MESSAGE, f"Unexpected error while processing message: {exception}", "Unexpected processing error"
        )
        self.assertIn("MSA|AE|0123456789", reply)

    def test_reply_returns_mllp_framed_string(self) -> None:
        exception = ValidationException("bad message")
        mock_event_logger = MagicMock()

        handler = ErrorHandler(exception, VALID_MESSAGE, mock_event_logger)
        reply = handler.reply()

        self.assertTrue(reply.startswith("\x0b"))
        self.assertTrue(reply.endswith("\x1c\r"))

    @patch("hl7_server.error_handler.logger")
    def test_reply_still_returns_nack_when_event_logger_raises(self, mock_logger: MagicMock) -> None:
        # EventLogger re-raises on telemetry send failure; that must not prevent the NACK from
        # being built and returned to the sender.
        exception = ValidationException("Message has wrong version")
        mock_event_logger = MagicMock()
        mock_event_logger.log_message_failed.side_effect = RuntimeError("App Insights unavailable")

        handler = ErrorHandler(exception, VALID_MESSAGE, mock_event_logger)
        reply = handler.reply()

        mock_event_logger.log_message_failed.assert_called_once()
        mock_logger.error.assert_any_call(
            "Failed to log message failure before sending NACK: %s", mock_event_logger.log_message_failed.side_effect
        )
        self.assertIn("MSA|AR|0123456789", reply)


if __name__ == "__main__":
    unittest.main()
