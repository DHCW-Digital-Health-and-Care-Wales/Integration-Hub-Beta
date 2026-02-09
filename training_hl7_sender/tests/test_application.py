import unittest
from unittest.mock import MagicMock

from training_hl7_sender.application import _process_message


class TestProcessMessage(unittest.TestCase):
    def setUp(self) -> None:
        self.test_hl7 = (
            "MSH|^~\\&|169|TRAINING_FAC|RECEIVER|RECEIVER_FAC|20260115120000||ADT^A31|MSG001|P|2.3.1\r"
            "EVN||20250502092900|20250505232332|||20250505232332\r"
            "PID|||12345678^^^TRAINING^PI||Reginald^John^Farqhar^Skuzmuncher^Mr||19850315|M\r"
        )

        # Sample ACK message (success)
        self.test_ack_success = (
            "MSH|^~\\&|RECEIVER|FAC|TRAINING_TRANSFORMER|FAC|20260125120001||ACK|12345|P|2.3.1\r"
            "MSA|AA|12345|Message accepted\r"
        )

        # Sample ACK message (failure)
        self.test_ack_failure = (
            "MSH|^~\\&|RECEIVER|FAC|TRAINING_TRANSFORMER|FAC|20260125120001||ACK|12345|P|2.3.1\r"
            "MSA|AE|12345|Application error\r"
        )

    def test_process_message_success(self) -> None:
        # Arrange
        mock_hl7_message = MagicMock()
        mock_hl7_message.body = [self.test_hl7.encode("utf-8")]

        mock_sender = MagicMock()
        mock_sender.send_message.return_value = self.test_ack_success

        # Act
        result = _process_message(mock_hl7_message, mock_sender)

        # Assert
        self.assertTrue(result)
        mock_sender.send_message.assert_called_once_with(self.test_hl7)

    def test_process_message_nack(self) -> None:
        # Arrange
        mock_hl7_message = MagicMock()
        mock_hl7_message.body = [self.test_hl7.encode("utf-8")]

        mock_sender = MagicMock()
        mock_sender.send_message.return_value = self.test_ack_failure

        # Act
        result = _process_message(mock_hl7_message, mock_sender)

        # Assert
        self.assertFalse(result)
        mock_sender.send_message.assert_called_once_with(self.test_hl7)

    def test_process_message_timeout(self) -> None:
        # Arrange
        mock_hl7_message = MagicMock()
        mock_hl7_message.body = [self.test_hl7.encode("utf-8")]

        mock_sender = MagicMock()
        mock_sender.send_message.side_effect = TimeoutError("Connection timed out")

        # Act
        result = _process_message(mock_hl7_message, mock_sender)

        # Assert
        self.assertFalse(result)

    def test_process_message_connection_error(self) -> None:
        # Arrange
        mock_hl7_message = MagicMock()
        mock_hl7_message.body = [self.test_hl7.encode("utf-8")]

        mock_sender = MagicMock()
        mock_sender.send_message.side_effect = ConnectionError("Failed to connect to server")

        # Act
        result = _process_message(mock_hl7_message, mock_sender)

        # Assert
        self.assertFalse(result)
