import unittest
from unittest.mock import MagicMock, patch

from azure.servicebus import ServiceBusMessage

from message_store_service.message_processor import process_message


class TestMessageProcessor(unittest.TestCase):
    def setUp(self) -> None:
        self.message_body = (
            "MSH|^~\\&|SENDING_APP|SENDING_FAC|RECEIVING_APP|RECEIVING_FAC|20250522103000||ADT^A01|MSGID1234|P|2.5"
        )
        self.service_bus_message = ServiceBusMessage(body=self.message_body)
        self.mock_event_logger = MagicMock()

    @patch("message_store_service.message_processor.logger")
    def test_process_message_success(self, mock_logger: MagicMock) -> None:
        # Arrange
        correlation_id = "test-correlation-123"
        message = ServiceBusMessage(body=self.message_body, correlation_id=correlation_id)

        # Act
        result = process_message(message, self.mock_event_logger)

        # Assert
        self.assertTrue(result)
        # Verify logger.info was called with correlation_id
        mock_logger.info.assert_called_once()
        log_call_args = mock_logger.info.call_args[0][0]
        self.assertIn(f"correlation_id={correlation_id}", log_call_args)

    @patch("message_store_service.message_processor.logger")
    def test_process_message_logs_on_exception(self, mock_logger: MagicMock) -> None:
        bad_message = MagicMock(spec=ServiceBusMessage)
        bad_message.correlation_id = "test-correlation-123"
        mock_logger.info.side_effect = Exception("Failed to log")

        # Act
        result = process_message(bad_message, self.mock_event_logger)

        # Assert
        self.assertFalse(result)
        mock_logger.error.assert_called()
        self.mock_event_logger.log_message_failed.assert_called_once()


if __name__ == "__main__":
    unittest.main()

