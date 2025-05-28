import unittest
from unittest.mock import MagicMock
from azure.servicebus import ServiceBusMessage

from dhcw_nhs_wales.inthub.msgbus.message_receiver_client import MessageReceiverClient


def create_message(message_id):
    message = MagicMock(spec=ServiceBusMessage)
    message.message_id = message_id
    return message


class TestMessageReceiverClient(unittest.TestCase):

    def setUp(self):
        self.service_bus_receiver_client = MagicMock()
        self.message_receiver_client = MessageReceiverClient(self.service_bus_receiver_client)

    def test_receive_messages_calls_complete_when_valid_message(self):
        # Arrange
        message = create_message("123")
        self.service_bus_receiver_client.receive_messages.return_value = [message]

        def processor(msg):
            return {"success": True}

        # Act
        self.message_receiver_client.receive_messages(1, processor)

        # Assert
        self.service_bus_receiver_client.complete_message.assert_called_once_with(message)
        self.service_bus_receiver_client.abandon_message.assert_not_called()

    def test_receive_messages_complete_and_dead_letter(self):
        # Arrange
        message1 = create_message("123")
        message2 = create_message("456")
        self.service_bus_receiver_client.receive_messages.return_value = [message1, message2]

        def processor(msg):
            if msg.message_id == "123":
                return {"success": True}
            return {"success": False, "retry": False, "error_reason": "Processing Error"}

        # Act
        self.message_receiver_client.receive_messages(2, processor)

        # Assert
        self.service_bus_receiver_client.complete_message.assert_called_once_with(message1)
        self.service_bus_receiver_client.abandon_message.assert_not_called()
        self.service_bus_receiver_client.dead_letter_message.assert_called_once()
        args, kwargs = self.service_bus_receiver_client.dead_letter_message.call_args
        self.assertEqual(args[0], message2)
        self.assertEqual(kwargs["reason"], "Processing Error")

    def test_receiveMessages_calls_deadLetter_when_message_fails_processing(self):
        # Arrange
        message = create_message("123")
        self.service_bus_receiver_client.receive_messages.return_value = [message]

        def processor(msg):
            if msg.message_id == "123":
                return {"success": False, "retry": False, "error_reason": "Processing Error"}

        # Act
        self.message_receiver_client.receive_messages(1, processor)

        self.service_bus_receiver_client.complete_message.assert_not_called()
        self.service_bus_receiver_client.dead_letter_message.assert_called_once()
        args, kwargs = self.service_bus_receiver_client.dead_letter_message.call_args
        self.assertEqual(args[0], message)
        self.assertEqual(kwargs["reason"], "Processing Error")

    def test_receiveMessages_calls_abandon_when_message_fails_processing_with_retry(self):
        # Arrange
        message = create_message("123")
        self.service_bus_receiver_client.receive_messages.return_value = [message]

        def processor(msg):
            if msg.message_id == "123":
                return {"success": False, "retry": True, "error_reason": "Pipe Parsing Error"}

        # Act
        self.message_receiver_client.receive_messages(1, processor)

        self.service_bus_receiver_client.complete_message.assert_not_called()
        self.service_bus_receiver_client.abandon_message.assert_called_once()

    def test_receiveMessages_calls_abandon_when_exception_during_processing(self):
        # Arrange
        message = create_message("123")
        self.service_bus_receiver_client.receive_messages.return_value = [message]

        def processor(msg):
            raise RuntimeError("Test Exception")

        # Act
        self.message_receiver_client.receive_messages(1, processor)

        self.service_bus_receiver_client.complete_message.assert_not_called()
        self.service_bus_receiver_client.abandon_message.assert_called_once()

    def test_exit_service_bus_receiver_client_closed(self):
        # Act
        self.service_bus_receiver_client.__exit__()

        # Assert
        self.service_bus_receiver_client.__exit__.assert_called_once()


if __name__ == '__main__':
    unittest.main()
