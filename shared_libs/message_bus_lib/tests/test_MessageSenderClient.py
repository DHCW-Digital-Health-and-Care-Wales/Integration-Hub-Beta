import unittest
from unittest.mock import MagicMock

from azure.servicebus.exceptions import (
    OperationTimeoutError,
)

from message_bus_lib.message_sender_client import MessageSenderClient


class TestMessageSenderClient(unittest.TestCase):

    def setUp(self) -> None:
        self.TOPIC_NAME = "test-topic"
        self.service_bus_sender_client = MagicMock()
        self.message_sender_client = MessageSenderClient(self.service_bus_sender_client, self.TOPIC_NAME)

    def test_send_message_sends_message_to_service_bus_without_session(self) -> None:
        # Arrange
        message = b"Test Message"

        # Act
        self.message_sender_client.send_message(message)

        # Assert
        self.service_bus_sender_client.send_messages.assert_called_once()
        messge_sent = self.service_bus_sender_client.send_messages.call_args[0][0]
        self.assertIsNone(messge_sent.session_id)

    def test_send_message_with_session(self) -> None:
        # Arrange
        message = b"Test Message"
        session_id = "test-session-id"
        message_sender_client = MessageSenderClient(
            self.service_bus_sender_client, self.TOPIC_NAME, session_id=session_id
        )

        # Act
        message_sender_client.send_message(message)

        # Assert
        self.service_bus_sender_client.send_messages.assert_called_once()
        messge_sent = self.service_bus_sender_client.send_messages.call_args[0][0]
        self.assertEqual(messge_sent.session_id, session_id)

    def test_send_message_retries_on_failure(self) -> None:
        # Arrange
        message = b"Test Message"
        self.service_bus_sender_client.send_messages = MagicMock(side_effect=OperationTimeoutError())

        # Act
        self.message_sender_client.send_message(message)

        # Assert
        self.assertEqual(len(self.service_bus_sender_client.send_messages.mock_calls), 3)

    def test_exit_service_bus_sender_client_closed(self) -> None:
        # Arrange
        exc_type = ValueError
        exc_value = ValueError("test error")
        exc_traceback = None

        # Act
        self.message_sender_client.__exit__(exc_type, exc_value, exc_traceback)

        # Assert
        self.service_bus_sender_client.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
