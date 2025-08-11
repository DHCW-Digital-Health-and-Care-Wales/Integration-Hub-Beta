import unittest
from unittest.mock import patch

from hl7_sender.ack_processor import get_ack_result


def generate_ack_msg(ack_code: str) -> str:
    return ("MSH|^~\\&|SENDER|SENDER_APP|RECEIVER|RECEIVER_APP|20250101000000||ACK^A01|123456|P|2.5\r"
            f"MSA|{ack_code}|123456\r")


class TestGetAckResult(unittest.TestCase):

    @patch('hl7_sender.ack_processor.logger')
    def test_valid_ack_aa(self, mock_logger) -> None:
        result = get_ack_result(generate_ack_msg("AA"))

        self.assertTrue(result)
        mock_logger.info.assert_called_once_with("Valid ACK received.")

    @patch('hl7_sender.ack_processor.logger')
    def test_valid_ack_ca(self, mock_logger) -> None:
        result = get_ack_result(generate_ack_msg("CA"))

        self.assertTrue(result)
        mock_logger.info.assert_called_once_with("Valid ACK received.")

    @patch('hl7_sender.ack_processor.logger')
    def test_negative_ack_ae(self, mock_logger) -> None:
        result = get_ack_result(generate_ack_msg("AE"))

        self.assertFalse(result)
        mock_logger.error.assert_called_once_with("Negative ACK received: AE for: 123456")

    @patch('hl7_sender.ack_processor.logger')
    def test_negative_ack_ar(self, mock_logger) -> None:
        result = get_ack_result(generate_ack_msg("AR"))

        self.assertFalse(result)
        mock_logger.error.assert_called_once_with("Negative ACK received: AR for: 123456")

    @patch('hl7_sender.ack_processor.logger')
    def test_non_ack_message(self, mock_logger) -> None:
        non_ack_message = (
            "MSH|^~\\&|SENDER|SENDER_APP|RECEIVER|RECEIVER_APP|20250101000000||ADT^A01|111111|P|2.5\r"
            "PID|1||123456^^^Hospital^MR||Doe^John\r"
        )

        result = get_ack_result(non_ack_message)

        self.assertFalse(result)
        mock_logger.error.assert_called_once_with('Received a non-ACK message')

    @patch('hl7_sender.ack_processor.logger')
    def test_malformed_message(self, mock_logger) -> None:
        result = get_ack_result("This is not a valid HL7 message")

        self.assertFalse(result)
        mock_logger.exception.assert_called_once_with('Exception while parsing ACK message')


if __name__ == '__main__':
    unittest.main()
