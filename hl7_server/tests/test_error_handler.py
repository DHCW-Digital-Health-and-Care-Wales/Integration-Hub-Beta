import unittest
from unittest.mock import MagicMock, patch

from hl7apy.mllp import InvalidHL7Message, UnsupportedMessageType

from hl7_server.error_handler import ErrorHandler


class TestErrorHandler(unittest.TestCase):
    @patch("hl7_server.error_handler.logger")
    def test_reply_with_unsupported_message_type(self, mock_logger) -> None:
        exception = UnsupportedMessageType("Unsupported type")
        unsupported_message = r"MSH|^~\&|GHH_ADT||||20080115153000||ADT^A01^ADT_A01|0123456789|P|2.5||||AL"
        mock_audit_client = MagicMock()

        handler = ErrorHandler(exception, unsupported_message, mock_audit_client)
        handler.incoming_message = unsupported_message

        with self.assertRaises(UnsupportedMessageType):
            handler.reply()

        mock_logger.error.assert_called_once_with(f"Unsupported Message Type: {exception}")
        mock_audit_client.log_message_failed.assert_called_once_with(
            unsupported_message, f"Unsupported Message Type: {exception}", "Unsupported message type"
        )

    @patch("hl7_server.error_handler.logger")
    def test_reply_with_invalid_hl7_message_exception(self, mock_logger) -> None:
        exception = InvalidHL7Message("invalid message")
        invalid_message = "<hello>"
        mock_audit_client = MagicMock()

        handler = ErrorHandler(exception, invalid_message, mock_audit_client)

        with self.assertRaises(InvalidHL7Message):
            handler.reply()

        mock_logger.error.assert_called_once_with(f"Invalid HL7 Message: {exception}")
        mock_audit_client.log_message_failed.assert_called_once_with(
            invalid_message, f"Invalid HL7 Message: {exception}", "Invalid HL7 message format"
        )


if __name__ == "__main__":
    unittest.main()
