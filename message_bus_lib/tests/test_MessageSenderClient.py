import unittest
from unittest.mock import MagicMock, Mock, call
from azure.servicebus import ServiceBusMessage

from dhcw.msgbus.MessageSenderClient import MessageSenderClient


class TestMessageSenderClient(unittest.TestCase):

    def setUp(self):
        self.TOPIC_NAME = "test-topic"
        self.service_bus_sender_client = MagicMock()
        self.message_sender_client = MessageSenderClient(self.service_bus_sender_client, self.TOPIC_NAME)

    def test_send_message_sends_message_to_service_bus(self):
        # Arrange
        message = "Test Message"
        binary_message = BinaryData.from_string(message)

        # Act
        self.message_sender_client.send_message(message)

        # Assert
        self.service_bus_sender_client.send_messages.assert_called_once()



    def test_close_service_bus_sender_client_closed(self):
        # Act
        self.message_sender_client.close()

        # Assert
        self.service_bus_sender_client.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()


class BinaryData:
    @staticmethod
    def from_string(data: str):
        return data