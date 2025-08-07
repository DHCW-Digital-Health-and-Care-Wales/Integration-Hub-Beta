import unittest
from unittest.mock import MagicMock, patch
from azure.servicebus import ServiceBusMessage

from message_bus_lib.message_receiver_client import MessageReceiverClient


def create_message(message_id):
    message = MagicMock(spec=ServiceBusMessage)
    message.message_id = message_id
    return message

class TestMessageReceiverClient(unittest.TestCase):

    def setUp(self):
        self.service_bus_receiver_client = MagicMock()
        self.message_receiver_client = MessageReceiverClient(self.service_bus_receiver_client)

    @patch("time.sleep", return_value=None)
    def test_receive_messages_calls_complete_when_valid_message(self, sleep_mock: MagicMock):
        # Arrange
        message = create_message("123")
        self.service_bus_receiver_client.receive_messages.return_value = [message]
        def processor(msg):
            return True

        # Act
        self.message_receiver_client.receive_messages(1, processor)

        # Assert
        self.service_bus_receiver_client.complete_message.assert_called_once_with(message)
        self.service_bus_receiver_client.abandon_message.assert_not_called()
        sleep_mock.assert_not_called()

    @patch("time.sleep", return_value=None)
    def test_receive_messages_complete_and_abandon(self, sleep_mock: MagicMock):
        # Arrange
        message1 = create_message("123")
        message2 = create_message("456")
        self.service_bus_receiver_client.receive_messages.side_effect = [[message1, message2], []]

        def processor(msg):
            return msg.message_id == "123"

        # Act
        self.message_receiver_client.receive_messages(2, processor)

        # Assert
        self.service_bus_receiver_client.complete_message.assert_called_once_with(message1)
        self.service_bus_receiver_client.abandon_message.assert_called_once_with(message2)

    @patch("time.sleep", return_value=None)
    def test_receiveMessages_calls_abandon_when_message_fails_processing(self, sleep_mock: MagicMock):
        # Arrange
        message = create_message("123")
        self.service_bus_receiver_client.receive_messages.side_effect = [[message], []]
        def processor(msg):
            return False

        # Act
        self.message_receiver_client.receive_messages(1, processor)

        self.service_bus_receiver_client.complete_message.assert_not_called()
        self.service_bus_receiver_client.abandon_message.assert_called_once_with(message)

    @patch("time.sleep", return_value=None)
    def test_receiveMessages_calls_abandon_when_exception_during_processing(self, sleep_mock: MagicMock):
        # Arrange
        message = create_message("123")
        self.service_bus_receiver_client.receive_messages.side_effect = [[message], []]

        def processor(msg):
            raise RuntimeError("Test Exception")

        # Act
        self.message_receiver_client.receive_messages(1, processor)

        self.service_bus_receiver_client.complete_message.assert_not_called()
        self.service_bus_receiver_client.abandon_message.assert_called_once_with(message)

    @patch("time.sleep", return_value=None)
    def test_receiveMessages_backoff_doubles_delay_on_each_retry(self, sleep_mock: MagicMock):
        # Arrange
        message = create_message("123")

        # Simulate 3 rounds: 2 failures, 1 empty to exit
        self.service_bus_receiver_client.receive_messages.side_effect = [[message], [message], []]

        def always_fail_processor(msg):
            return False

        # Act
        self.message_receiver_client.receive_messages(1, always_fail_processor)

        # Assert
        self.assertEqual(sleep_mock.call_count, 2)
        sleep_mock.assert_any_call(self.message_receiver_client.INITIAL_DELAY_SECONDS)
        sleep_mock.assert_any_call(self.message_receiver_client.INITIAL_DELAY_SECONDS * 2)
        self.assertEqual(self.message_receiver_client.delay, self.message_receiver_client.INITIAL_DELAY_SECONDS * 4)

    @patch("time.sleep", return_value=None)
    def test_receiveMessages_backoff_called_on_exception(self, sleep_mock: MagicMock):
        # Arrange
        message = create_message("123")

        # Simulate 2 rounds: 1 exception, then exit
        self.service_bus_receiver_client.receive_messages.side_effect = [[message], []]

        def error_processor(msg):
            raise RuntimeError("Processing failed")

        # Act
        self.message_receiver_client.receive_messages(1, error_processor)

        # Assert
        sleep_mock.assert_called_once_with(self.message_receiver_client.INITIAL_DELAY_SECONDS)
        self.assertEqual(self.message_receiver_client.retry_attempt, 1)
        self.assertEqual(self.message_receiver_client.delay, self.message_receiver_client.INITIAL_DELAY_SECONDS * 2)

    @patch("time.sleep", return_value=None)
    def test_receiveMessages_backoff_delay_does_not_exceed_max(self, sleep_mock: MagicMock):
        # Arrange
        message = create_message("123")

        # Simulate 10 failed receives, then exit
        self.service_bus_receiver_client.receive_messages.side_effect = [[message]] * 10 + [[]]

        def fail_processor(msg):
            return False

        # Act
        self.message_receiver_client.receive_messages(1, fail_processor)

        # Assert
        self.assertEqual(sleep_mock.call_count, 10)
        final_delay = self.message_receiver_client.delay
        self.assertLessEqual(final_delay, self.message_receiver_client.MAX_DELAY_SECONDS)

    @patch("time.sleep", return_value=None)
    def test_receiveMessages_backoff_delay_exits_after_success(self, sleep_mock: MagicMock):
        # Arrange
        message1 = create_message("123")
        message2 = create_message("456")
        message3 = create_message("789")

        # 1st: success → no retry
        # 2nd: failure → retry
        # 3rd: success → exit
        self.service_bus_receiver_client.receive_messages.side_effect = [[message1, message2], [message3]]

        def processor(msg):
            return msg.message_id != "456"
        # Act
        self.message_receiver_client.receive_messages(4, processor)

        # Assert
        self.assertEqual(2, self.service_bus_receiver_client.complete_message.call_count)
        self.service_bus_receiver_client.complete_message.assert_any_call(message1)
        self.service_bus_receiver_client.complete_message.assert_any_call(message3)

        self.service_bus_receiver_client.abandon_message.assert_called_once_with(message2)

        sleep_mock.assert_called_once_with(self.message_receiver_client.INITIAL_DELAY_SECONDS)

        # Ensure delay is reset after last success
        self.assertEqual(self.message_receiver_client.delay, self.message_receiver_client.INITIAL_DELAY_SECONDS)

        # Final retry_attempt should also reset to 0
        self.assertEqual(self.message_receiver_client.retry_attempt, 0)

    def test_exit_service_bus_receiver_client_closed(self):
        # Arrange
        exc_type = ValueError
        exc_value = ValueError("test error")
        exc_traceback = None

        # Act
        self.message_receiver_client.__exit__(exc_type, exc_value, exc_traceback)

        # Assert
        self.service_bus_receiver_client.close.assert_called_once()

if __name__ == '__main__':
    unittest.main()
