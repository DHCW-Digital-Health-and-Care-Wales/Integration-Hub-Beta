import unittest
from typing import Any
from unittest.mock import MagicMock, patch

from azure.servicebus import ServiceBusMessage
from azure.servicebus.exceptions import ServiceBusError, SessionCannotBeLockedError

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
    def test_receive_messages_sets_retry_delay_on_service_bus_error(self, sleep_mock: MagicMock) -> None:
        # Arrange
        self.service_bus_receiver_client.receive_messages.side_effect = ServiceBusError("Transient receive failure")

        # Act
        self.message_receiver_client.receive_messages(1, lambda msg: True)

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


class TestReceiveMessagesBatch(unittest.TestCase):
    """Tests for MessageReceiverClient.receive_messages_batch with batch callback."""

    def setUp(self) -> None:
        self.service_bus_client = MagicMock()
        self.sb_receiver = self.service_bus_client.get_queue_receiver.return_value.__enter__.return_value
        self.message_receiver_client = MessageReceiverClient(self.service_bus_client, "test-queue")

    @patch("time.sleep", return_value=None)
    def test_receive_messages_batch_completes_all_on_success(self, sleep_mock: MagicMock) -> None:
        """When batch_processor returns True, all messages should be completed."""
        messages = [create_message("1"), create_message("2"), create_message("3")]
        self.sb_receiver.receive_messages.return_value = messages

        def processor(msgs: list) -> bool:
            self.assertEqual(len(msgs), 3)
            return True

        self.message_receiver_client.receive_messages_batch(num_of_messages=10, batch_processor=processor)

        self.assertEqual(self.sb_receiver.complete_message.call_count, 3)
        self.sb_receiver.complete_message.assert_any_call(messages[0])
        self.sb_receiver.complete_message.assert_any_call(messages[1])
        self.sb_receiver.complete_message.assert_any_call(messages[2])
        self.sb_receiver.abandon_message.assert_not_called()

    @patch("time.sleep", return_value=None)
    def test_receive_messages_batch_abandons_all_on_failure(self, sleep_mock: MagicMock) -> None:
        """When batch_processor returns False, all messages should be abandoned."""
        messages = [create_message("1"), create_message("2")]
        self.sb_receiver.receive_messages.return_value = messages

        def processor(msgs: list) -> bool:
            return False

        self.message_receiver_client.receive_messages_batch(num_of_messages=10, batch_processor=processor)

        self.assertEqual(self.sb_receiver.abandon_message.call_count, 2)
        self.sb_receiver.abandon_message.assert_any_call(messages[0])
        self.sb_receiver.abandon_message.assert_any_call(messages[1])
        self.sb_receiver.complete_message.assert_not_called()

    @patch("time.sleep", return_value=None)
    def test_receive_messages_batch_abandons_all_on_exception(self, sleep_mock: MagicMock) -> None:
        """When batch_processor raises an exception, all messages should be abandoned."""
        messages = [create_message("1"), create_message("2")]
        self.sb_receiver.receive_messages.return_value = messages

        def processor(msgs: list) -> bool:
            raise RuntimeError("Processing failed")

        self.message_receiver_client.receive_messages_batch(num_of_messages=10, batch_processor=processor)

        self.assertEqual(self.sb_receiver.abandon_message.call_count, 2)
        self.sb_receiver.complete_message.assert_not_called()

    @patch("time.sleep", return_value=None)
    def test_receive_messages_batch_skips_processing_when_no_messages(self, sleep_mock: MagicMock) -> None:
        """When no messages are received, batch_processor should not be called."""
        self.sb_receiver.receive_messages.return_value = []

        processor = MagicMock(return_value=True)

        self.message_receiver_client.receive_messages_batch(num_of_messages=10, batch_processor=processor)

        processor.assert_not_called()
        self.sb_receiver.complete_message.assert_not_called()
        self.sb_receiver.abandon_message.assert_not_called()


class TestAutoLockRenewerLifecycle(unittest.TestCase):
    """
    Tests that AutoLockRenewer.close() is always called when a session_id is provided,
    regardless of whether processing succeeds, fails, or raises an unexpected exception.
    This ensures background lock-renewal threads are never leaked.
    """

    def setUp(self) -> None:
        self.service_bus_client = MagicMock()
        self.sb_receiver = self.service_bus_client.get_queue_receiver.return_value.__enter__.return_value
        # Use a session_id so that AutoLockRenewer is instantiated inside _receive_and_process.
        self.message_receiver_client = MessageReceiverClient(
            self.service_bus_client, "test-queue", session_id="session-1"
        )

    @patch("message_bus_lib.message_receiver_client.AutoLockRenewer")
    @patch("time.sleep", return_value=None)
    def test_autolock_renewer_closed_after_processing(self, _sleep: MagicMock, mock_renewer_cls: MagicMock) -> None:
        """AutoLockRenewer must be closed regardless of whether processing succeeds,
        returns False, or raises an exception."""

        def raising_processor(msg: Any) -> bool:
            raise RuntimeError("Unexpected processing error")

        cases = [
            ("success", lambda msg: True),
            ("failure", lambda msg: False),
            ("exception", raising_processor),
        ]

        for scenario, processor in cases:
            with self.subTest(scenario=scenario):
                mock_renewer = MagicMock()
                mock_renewer_cls.reset_mock()
                mock_renewer_cls.return_value = mock_renewer

                # Reset retry state so _apply_delay_and_check_if_its_retry_time
                # does not short-circuit before AutoLockRenewer is created.
                self.message_receiver_client.next_retry_time = None
                self.message_receiver_client.retry_attempt = 0
                self.sb_receiver.receive_messages.return_value = [create_message("1")]

                self.message_receiver_client.receive_messages(1, processor)

                mock_renewer.close.assert_called_once()

    @patch("message_bus_lib.message_receiver_client.AutoLockRenewer")
    @patch("time.sleep", return_value=None)
    def test_autolock_renewer_closed_when_receiver_creation_raises(
        self, _sleep: MagicMock, mock_renewer_cls: MagicMock
    ) -> None:
        """AutoLockRenewer must be closed and retry scheduled when receiver creation raises."""
        mock_renewer = MagicMock()
        mock_renewer_cls.return_value = mock_renewer

        # Simulate an error during receiver __enter__ (e.g., network failure)
        self.service_bus_client.get_queue_receiver.return_value.__enter__.side_effect = RuntimeError(
            "Receiver creation failed"
        )

        # Should NOT raise — unexpected exceptions are now caught and retried
        self.message_receiver_client.receive_messages(1, lambda msg: True)

        # AutoLockRenewer must still be closed via the finally block
        mock_renewer.close.assert_called_once()
        # A retry must have been scheduled
        self.assertIsNotNone(self.message_receiver_client.next_retry_time)

    @patch("message_bus_lib.message_receiver_client.AutoLockRenewer")
    @patch("time.sleep", return_value=None)
    def test_autolock_renewer_closed_on_session_cannot_be_locked(
        self, _sleep: MagicMock, mock_renewer_cls: MagicMock
    ) -> None:
        """AutoLockRenewer must be closed when SessionCannotBeLockedError is raised."""
        mock_renewer = MagicMock()
        mock_renewer_cls.return_value = mock_renewer

        self.service_bus_client.get_queue_receiver.return_value.__enter__.side_effect = SessionCannotBeLockedError()

        # SessionCannotBeLockedError is caught internally; no exception should propagate.
        self.message_receiver_client.receive_messages(1, lambda msg: True)

        mock_renewer.close.assert_called_once()

    @patch("message_bus_lib.message_receiver_client.AutoLockRenewer")
    @patch("time.sleep", return_value=None)
    def test_autolock_renewer_not_created_without_session_id(
        self, _sleep: MagicMock, mock_renewer_cls: MagicMock
    ) -> None:
        """AutoLockRenewer must NOT be created when no session_id is provided."""
        # Create a client without a session_id
        client_without_session = MessageReceiverClient(self.service_bus_client, "test-queue")
        sb_receiver = self.service_bus_client.get_queue_receiver.return_value.__enter__.return_value
        sb_receiver.receive_messages.return_value = []

        client_without_session.receive_messages(1, lambda msg: True)

        mock_renewer_cls.assert_not_called()


if __name__ == "__main__":
    unittest.main()
