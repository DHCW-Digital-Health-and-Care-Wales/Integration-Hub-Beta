import unittest
from unittest.mock import MagicMock

from message_bus_lib.message_sender_client import MessageSenderClient


class TestMessageSenderClient(unittest.TestCase):

    def setUp(self):
        self.TOPIC_NAME = "test-topic"
        self.service_bus_sender_client = MagicMock()
        self.message_sender_client = MessageSenderClient(self.service_bus_sender_client, self.TOPIC_NAME)

    def test_send_message_sends_message_to_service_bus(self):
        # Arrange
        message = "Test Message"

        # Act
        self.message_sender_client.send_message(message)

        # Assert
        self.service_bus_sender_client.send_messages.assert_called_once()

    def test_exit_service_bus_sender_client_closed(self):
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
