import unittest
from typing import Any
from unittest.mock import MagicMock, patch

from azure.servicebus import ServiceBusMessage

from message_bus_lib.message_receiver_client import MessageReceiverClient


def create_message(message_id: str) -> MagicMock:
    message = MagicMock(spec=ServiceBusMessage)
    message.message_id = message_id
    return message

TIMESTAMP_IN_PAST = 1760047200.0  # Fixed timestamp for testing

class TestMessageReceiverClient(unittest.TestCase):


    def setUp(self) -> None:
        service_bus_client = MagicMock()
        self.service_bus_receiver_client = service_bus_client.get_queue_receiver.return_value.__enter__.return_value
        queue_name = "test-queue"
        self.message_receiver_client = MessageReceiverClient(service_bus_client, queue_name)

    @patch("time.sleep", return_value=None)
    def test_receive_messages_calls_complete_when_valid_message(self, sleep_mock: MagicMock) -> None:
        # Arrange
        message = create_message("123")
        self.service_bus_receiver_client.receive_messages.return_value = [message]

        def processor(msg: Any) -> bool:
            return True

        # Act
        self.message_receiver_client.receive_messages(1, processor)

        # Assert
        self.service_bus_receiver_client.complete_message.assert_called_once_with(message)
        self.service_bus_receiver_client.abandon_message.assert_not_called()
        sleep_mock.assert_not_called()

    @patch("time.sleep", return_value=None)
    def test_receive_messages_complete_and_abandon(self, sleep_mock: MagicMock) -> None:
        # Arrange
        message1 = create_message("123")
        message2 = create_message("456")
        self.service_bus_receiver_client.receive_messages.side_effect = [[message1, message2], []]

        def processor(msg: Any) -> bool:
            return msg.message_id == "123"

        # Act
        self.message_receiver_client.receive_messages(2, processor)

        # Assert
        self.service_bus_receiver_client.complete_message.assert_called_once_with(message1)
        self.service_bus_receiver_client.abandon_message.assert_called_once_with(message2)

    @patch("time.sleep", return_value=None)
    def test_receive_messages_abandons_all_subsequent_messages_on_failure(self, sleep_mock: MagicMock) -> None:
        # Arrange
        message1 = create_message("123")
        message2 = create_message("456")
        message3 = create_message("789")
        self.service_bus_receiver_client.receive_messages.side_effect = [[message1, message2, message3], []]

        def processor(msg: Any) -> bool:
            return msg.message_id == "123"

        # Act
        self.message_receiver_client.receive_messages(4, processor)

        # Assert
        self.service_bus_receiver_client.complete_message.assert_called_once_with(message1)

        self.assertEqual(self.service_bus_receiver_client.abandon_message.call_count, 2)
        self.service_bus_receiver_client.abandon_message.assert_any_call(message2)
        self.service_bus_receiver_client.abandon_message.assert_any_call(message3)
        self.assertIsNotNone(self.message_receiver_client.next_retry_time)

    @patch("time.sleep", return_value=None)
    def test_receive_messages_abandons_all_subsequent_on_exception(self, sleep_mock: MagicMock) -> None:
        # Arrange
        message1 = create_message("123")
        message2 = create_message("456")
        message3 = create_message("789")
        self.service_bus_receiver_client.receive_messages.side_effect = [[message1, message2, message3], []]

        def processor(msg: Any) -> bool:
            if msg.message_id == "456":
                raise RuntimeError("Processing failed")
            return True

        # Act
        self.message_receiver_client.receive_messages(3, processor)

        # Assert
        self.service_bus_receiver_client.complete_message.assert_called_once_with(message1)

        self.assertEqual(self.service_bus_receiver_client.abandon_message.call_count, 2)
        self.service_bus_receiver_client.abandon_message.assert_any_call(message2)
        self.service_bus_receiver_client.abandon_message.assert_any_call(message3)
        self.assertIsNotNone(self.message_receiver_client.next_retry_time)

    @patch("time.sleep", return_value=None)
    def test_receiveMessages_backoff_doubles_delay_on_each_retry(self, sleep_mock: MagicMock) -> None:
        # Arrange
        message = create_message("123")

        # Simulate previous failure
        self.message_receiver_client.retry_attempt = 1
        self.message_receiver_client.next_retry_time = TIMESTAMP_IN_PAST
        self.message_receiver_client.delay = 10

        # Simulate 3 rounds: 2 failures, 1 empty to exit
        self.service_bus_receiver_client.receive_messages.return_value = [message]

        def always_fail_processor(msg: Any) -> bool:
            return False

        # Act
        self.message_receiver_client.receive_messages(1, always_fail_processor)

        # Assert
        self.assertEqual(self.message_receiver_client.delay, 10 * 2)

    @patch("time.sleep", return_value=None)
    def test_receiveMessages_backoff_called_on_exception(self, sleep_mock: MagicMock) -> None:
        # Arrange
        message = create_message("123")

        # Simulate 2 rounds: 1 exception, then exit
        self.service_bus_receiver_client.receive_messages.side_effect = [[message], []]

        def error_processor(msg: Any) -> bool:
            raise RuntimeError("Processing failed")

        # Act
        self.message_receiver_client.receive_messages(1, error_processor)
        self.message_receiver_client.receive_messages(1, error_processor)

        # Assert
        self.assertEqual(self.message_receiver_client.retry_attempt, 1)
        self.assertEqual(self.message_receiver_client.delay, self.message_receiver_client.INITIAL_DELAY_SECONDS * 2)
        self.assertIsNotNone(self.message_receiver_client.next_retry_time)

    @patch("time.sleep", return_value=None)
    def test_receiveMessages_backoff_delay_does_not_exceed_max(self, sleep_mock: MagicMock) -> None:
        # Arrange
        message = create_message("123")
        # Simulate previous failure
        self.message_receiver_client.retry_attempt = 1
        self.message_receiver_client.next_retry_time = TIMESTAMP_IN_PAST
        self.message_receiver_client.delay = self.message_receiver_client.MAX_DELAY_SECONDS - 1

        # Simulate 10 failed receives, then exit
        self.service_bus_receiver_client.receive_messages.return_value = [message]

        def fail_processor(msg: Any) -> bool:
            return False

        # Act
        self.message_receiver_client.receive_messages(1, fail_processor)

        # Assert
        final_delay = self.message_receiver_client.delay
        self.assertLessEqual(final_delay, self.message_receiver_client.MAX_DELAY_SECONDS)

    @patch("time.sleep", return_value=None)
    def test_receiveMessages_backoff_delay_exits_after_success(self, sleep_mock: MagicMock) -> None:
        # Arrange
        message = create_message("123")
        self.service_bus_receiver_client.receive_messages.side_effect = [[message]]
        # Simulate previous failure
        self.message_receiver_client.retry_attempt = 1
        self.message_receiver_client.next_retry_time = TIMESTAMP_IN_PAST
        self.message_receiver_client.delay = self.message_receiver_client.INITIAL_DELAY_SECONDS * 2

        def processor(msg: ServiceBusMessage) -> bool:
            return msg.message_id != "456"

        # Act
        self.message_receiver_client.receive_messages(4, processor)

        # Assert
        self.assertEqual(1, self.service_bus_receiver_client.complete_message.call_count)

        # Ensure delay is reset after last success
        self.assertEqual(self.message_receiver_client.delay, self.message_receiver_client.INITIAL_DELAY_SECONDS)
        # Final retry_attempt should also reset to 0
        self.assertEqual(self.message_receiver_client.retry_attempt, 0)
        # there should be no retry planned
        self.assertIsNone(self.message_receiver_client.next_retry_time)

if __name__ == '__main__':
    unittest.main()
