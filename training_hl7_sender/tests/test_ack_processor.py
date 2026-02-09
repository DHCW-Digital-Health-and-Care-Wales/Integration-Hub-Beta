import unittest
from unittest.mock import MagicMock, patch

from training_hl7_sender.ack_processor import get_ack_result


class TestAckProcessor(unittest.TestCase):
    def setUp(self) -> None:
        self.test_ack_success = (
            "MSH|^~\\&|SENDER|SENDER_FACILITY|RECEIVER|RECEIVER_FACILITY|"
            "202406101200||ACK^A01|123456|P|2.5\rMSA|AA|123456\r"
        )

        self.test_ack_failure = (
            "MSH|^~\\&|SENDER|SENDER_FACILITY|RECEIVER|RECEIVER_FACILITY|"
            "202406101200||ACK^A01|123456|P|2.5\rMSA|AE|123456\r"
        )

        self.test_missing_msa_ack_failure = (
            "MSH|^~\\&|SENDER|SENDER_FACILITY|RECEIVER|RECEIVER_FACILITY|202406101200||ACK^A01|123456|P|2.5\r"
        )

        self.test_malformed_message = "EIVER|RECEIVER_FACILITY|202406101K^A01|123456|P|2.5\r"

    @patch("training_hl7_sender.ack_processor.logger")
    def test_get_ack_result_success(self, mock_logger: MagicMock) -> None:
        result = get_ack_result(self.test_ack_success)
        self.assertTrue(result)
        mock_logger.info.assert_called_with("Message acknowledged successfully.")

    @patch("training_hl7_sender.ack_processor.logger")
    def test_get_ack_result_failure(self, mock_logger: MagicMock) -> None:
        result = get_ack_result(self.test_ack_failure)
        self.assertFalse(result)
        mock_logger.error.assert_called_with("Negative ACK Code received: AE, for message control ID: 123456")

    @patch("training_hl7_sender.ack_processor.logger")
    def test_get_ack_result_missing_msa(self, mock_logger: MagicMock) -> None:
        result = get_ack_result(self.test_missing_msa_ack_failure)
        self.assertFalse(result)
        mock_logger.error.assert_called_with("Missing MSA segment.")

    @patch("training_hl7_sender.ack_processor.logger")
    def test_get_ack_result_invalid_message(self, mock_logger: MagicMock) -> None:
        result = get_ack_result(self.test_malformed_message)
        self.assertFalse(result)
        mock_logger.error.assert_called_with("Error processing ACK message: Invalid message")
