import unittest
from typing import Any
from unittest.mock import MagicMock, patch

from azure.servicebus import ServiceBusMessage
from azure.servicebus.exceptions import SessionCannotBeLockedError

from message_bus_lib.subscription_receiver_client import SubscriptionReceiverClient


def create_message(message_id: str) -> MagicMock:
    message = MagicMock(spec=ServiceBusMessage)
    message.message_id = message_id
    return message

TIMESTAMP_IN_PAST = 1760047200.0  # Fixed timestamp for testing


class TestSubscriptionReceiverClient(unittest.TestCase):
    def setUp(self) -> None:
        self.service_bus_client = MagicMock()
        self.service_bus_receiver_client = (
            self.service_bus_client.get_subscription_receiver.return_value
            .__enter__.return_value
        )
        self.topic_name = "test-topic"
        self.subscription_name = "test-subscription"
        self.session_id = "test-session"

        self.subscription_receiver_client = SubscriptionReceiverClient(
            self.service_bus_client,
            topic_name=self.topic_name,
            subscription_name=self.subscription_name,
            session_id=self.session_id,
        )


    def test_initializes_subscription_attributes(self) -> None:
        expected_attributes = {
            "topic_name": self.topic_name,
            "subscription_name": self.subscription_name,
            "session_id": self.session_id,
        }

        for attribute_name, expected_value in expected_attributes.items():
            with self.subTest(attribute_name=attribute_name):
                self.assertEqual(getattr(self.subscription_receiver_client, attribute_name), expected_value)


    @patch("time.sleep", return_value=None)
    def test_receive_messages_calls_complete_when_valid_message(self, sleep_mock: MagicMock) -> None:
        # Arrange
        message = create_message("123")
        self.service_bus_receiver_client.receive_messages.return_value = [message]

        def processor(msg: Any) -> bool:
            return True

        # Act
        self.subscription_receiver_client.receive_messages(1, processor)

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
        self.subscription_receiver_client.receive_messages(2, processor)

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
        self.subscription_receiver_client.receive_messages(4, processor)

        # Assert
        self.service_bus_receiver_client.complete_message.assert_called_once_with(message1)

        self.assertEqual(self.service_bus_receiver_client.abandon_message.call_count, 2)
        self.service_bus_receiver_client.abandon_message.assert_any_call(message2)
        self.service_bus_receiver_client.abandon_message.assert_any_call(message3)
        self.assertIsNotNone(self.subscription_receiver_client.next_retry_time)


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
        self.subscription_receiver_client.receive_messages(3, processor)

        # Assert
        self.service_bus_receiver_client.complete_message.assert_called_once_with(message1)

        self.assertEqual(self.service_bus_receiver_client.abandon_message.call_count, 2)
        self.service_bus_receiver_client.abandon_message.assert_any_call(message2)
        self.service_bus_receiver_client.abandon_message.assert_any_call(message3)
        self.assertIsNotNone(self.subscription_receiver_client.next_retry_time)


    @patch("time.sleep", return_value=None)
    def test_receiveMessages_backoff_doubles_delay_on_each_retry(self, sleep_mock: MagicMock) -> None:
        # Arrange
        message = create_message("123")

        # Simulate previous failure
        self.subscription_receiver_client.retry_attempt = 1
        self.subscription_receiver_client.next_retry_time = TIMESTAMP_IN_PAST
        self.subscription_receiver_client.delay = 10

        # Simulate 3 rounds: 2 failures, 1 empty to exit
        self.service_bus_receiver_client.receive_messages.return_value = [message]

        def always_fail_processor(msg: Any) -> bool:
            return False

        # Act
        self.subscription_receiver_client.receive_messages(1, always_fail_processor)

        # Assert
        self.assertEqual(self.subscription_receiver_client.delay, 10 * 2)


class TestMessageReceiverClient(unittest.TestCase):
    def setUp(self) -> None:
        self.service_bus_client = MagicMock()
        self.service_bus_receiver_client = (
            self.service_bus_client.get_subscription_receiver.return_value
            .__enter__.return_value
        )
        self.topic_name = "test-topic"
        self.subscription_name = "test-subscription"
        self.session_id = "test-session"

        self.subscription_receiver_client = SubscriptionReceiverClient(
            self.service_bus_client,
            topic_name=self.topic_name,
            subscription_name=self.subscription_name,
            session_id=self.session_id,
        )


    @patch("time.sleep", return_value=None)
    def test_receive_messages_batch_completes_all_on_success(self, sleep_mock: MagicMock) -> None:
        """When batch_processor returns True, all messages should be completed."""
        messages = [create_message("1"), create_message("2"), create_message("3")]
        self.service_bus_receiver_client.receive_messages.return_value = messages

        def processor(msgs: list) -> bool:
            self.assertEqual(len(msgs), 3)
            return True

        self.subscription_receiver_client.receive_messages_batch(num_of_messages=10, batch_processor=processor)

        self.assertEqual(self.service_bus_receiver_client.complete_message.call_count, 3)
        self.service_bus_receiver_client.complete_message.assert_any_call(messages[0])
        self.service_bus_receiver_client.complete_message.assert_any_call(messages[1])
        self.service_bus_receiver_client.complete_message.assert_any_call(messages[2])
        self.service_bus_receiver_client.abandon_message.assert_not_called()


    @patch("time.sleep", return_value=None)
    def test_receive_messages_batch_abandons_all_on_failure(self, sleep_mock: MagicMock) -> None:
        """When batch_processor returns False, all messages should be abandoned."""
        messages = [create_message("1"), create_message("2")]
        self.service_bus_receiver_client.receive_messages.return_value = messages

        def processor(msgs: list) -> bool:
            return False

        self.subscription_receiver_client.receive_messages_batch(num_of_messages=10, batch_processor=processor)

        self.assertEqual(self.service_bus_receiver_client.abandon_message.call_count, 2)
        self.service_bus_receiver_client.abandon_message.assert_any_call(messages[0])
        self.service_bus_receiver_client.abandon_message.assert_any_call(messages[1])
        self.service_bus_receiver_client.complete_message.assert_not_called()


    @patch("time.sleep", return_value=None)
    def test_receive_messages_batch_abandons_all_on_exception(self, sleep_mock: MagicMock) -> None:
        """When batch_processor raises an exception, all messages should be abandoned."""
        messages = [create_message("1"), create_message("2")]
        self.service_bus_receiver_client.receive_messages.return_value = messages

        def processor(msgs: list) -> bool:
            raise RuntimeError("Processing failed")

        self.subscription_receiver_client.receive_messages_batch(num_of_messages=10, batch_processor=processor)

        self.assertEqual(self.service_bus_receiver_client.abandon_message.call_count, 2)
        self.service_bus_receiver_client.complete_message.assert_not_called()


    @patch("time.sleep", return_value=None)
    def test_receive_messages_batch_skips_processing_when_no_messages(self, sleep_mock: MagicMock) -> None:
        """When no messages are received, batch_processor should not be called."""
        self.service_bus_receiver_client.receive_messages.return_value = []

        processor = MagicMock(return_value=True)

        self.subscription_receiver_client.receive_messages_batch(num_of_messages=10, batch_processor=processor)

        processor.assert_not_called()
        self.service_bus_receiver_client.complete_message.assert_not_called()
        self.service_bus_receiver_client.abandon_message.assert_not_called()


class TestAutoLockRenewerLifecycle(unittest.TestCase):
    def setUp(self) -> None:
        self.service_bus_client = MagicMock()
        self.service_bus_receiver_client = (
            self.service_bus_client.get_subscription_receiver.return_value
            .__enter__.return_value
        )
        self.topic_name = "test-topic"
        self.subscription_name = "test-subscription"
        self.session_id = "test-session"

        self.subscription_receiver_client = SubscriptionReceiverClient(
            self.service_bus_client,
            topic_name=self.topic_name,
            subscription_name=self.subscription_name,
            session_id=self.session_id,
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
                self.subscription_receiver_client.next_retry_time = None
                self.subscription_receiver_client.retry_attempt = 0
                self.service_bus_client.receive_messages.return_value = [create_message("1")]

                self.subscription_receiver_client.receive_messages(1, processor)

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
        self.service_bus_client.get_subscription_receiver.return_value.__enter__.side_effect = RuntimeError(
            "Receiver creation failed"
        )

        # Should NOT raise — unexpected exceptions are now caught and retried
        self.subscription_receiver_client.receive_messages(1, lambda msg: True)

        # AutoLockRenewer must still be closed via the finally block
        mock_renewer.close.assert_called_once()
        # A retry must have been scheduled
        self.assertIsNotNone(self.subscription_receiver_client.next_retry_time)


    @patch("message_bus_lib.message_receiver_client.AutoLockRenewer")
    @patch("time.sleep", return_value=None)
    def test_autolock_renewer_closed_on_session_cannot_be_locked(
        self, _sleep: MagicMock, mock_renewer_cls: MagicMock
    ) -> None:
        """AutoLockRenewer must be closed when SessionCannotBeLockedError is raised."""
        mock_renewer = MagicMock()
        mock_renewer_cls.return_value = mock_renewer

        receiver_mock = self.service_bus_client.get_subscription_receiver.return_value
        receiver_mock.__enter__.side_effect = SessionCannotBeLockedError()

        # SessionCannotBeLockedError is caught internally; no exception should propagate.
        self.subscription_receiver_client.receive_messages(1, lambda msg: True)

        mock_renewer.close.assert_called_once()


    @patch("message_bus_lib.message_receiver_client.AutoLockRenewer")
    @patch("time.sleep", return_value=None)
    def test_autolock_renewer_not_created_without_session_id(
        self, _sleep: MagicMock, mock_renewer_cls: MagicMock
    ) -> None:
        """AutoLockRenewer must NOT be created when no session_id is provided."""
        # Create a client without a session_id
        client_without_session = SubscriptionReceiverClient(
            self.service_bus_client, self.topic_name, self.subscription_name
        )
        sb_receiver = self.service_bus_client.get_subscription_receiver.return_value.__enter__.return_value
        sb_receiver.receive_messages.return_value = []

        client_without_session.receive_messages(1, lambda msg: True)

        mock_renewer_cls.assert_not_called()


if __name__ == "__main__":
    unittest.main()
