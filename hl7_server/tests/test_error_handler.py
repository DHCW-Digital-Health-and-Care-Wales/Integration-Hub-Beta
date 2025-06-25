import unittest
from unittest.mock import patch

from hl7apy.mllp import InvalidHL7Message, UnsupportedMessageType

from hl7_server.error_handler import ErrorHandler


class TestErrorHandler(unittest.TestCase):
    @patch("hl7_server.error_handler.logger")
    def test_reply_with_unsupported_message_type(self, mock_logger):
        exception = UnsupportedMessageType("Unsupported type")
        unsupported_message = r"MSH|^~\&|GHH_ADT||||20080115153000||ADT^A01^ADT_A01|0123456789|P|2.5||||AL"
        handler = ErrorHandler(exc=exception, message=unsupported_message)

        handler.reply()

        mock_logger.error.assert_called_once_with("Unsupported Message Type: %s", exception)

    @patch("hl7_server.error_handler.logger")
    def test_reply_with_invalid_hl7_message_exception(self, mock_logger):
        exception = InvalidHL7Message("invalid message")
        invalid_message = "<hello>"
        handler = ErrorHandler(exc=exception, message=invalid_message)

        handler.reply()

        mock_logger.error.assert_called_once_with("Invalid HL7 Message: %s", exception)


if __name__ == "__main__":
    unittest.main()
