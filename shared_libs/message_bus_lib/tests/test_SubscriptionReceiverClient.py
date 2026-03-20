import unittest
from unittest.mock import MagicMock, patch

from azure.servicebus import ServiceBusMessage
from azure.servicebus.exceptions import SessionCannotBeLockedError

from message_bus_lib.subscription_receiver_client import SubscriptionReceiverClient


def create_message(message_id: str) -> MagicMock:
    message = MagicMock(spec=ServiceBusMessage)
    message.message_id = message_id
    return message


class TestSubscriptionReceiverClient(unittest.TestCase):
    def setUp(self) -> None:
        self.service_bus_client = MagicMock()
        self.sb_receiver = self.service_bus_client.get_subscription_receiver.return_value.__enter__.return_value
        self.client = SubscriptionReceiverClient(
            self.service_bus_client,
            topic_name="test-topic",
            subscription_name="test-subscription",
            session_id="session-1",
        )

    @patch("time.sleep", return_value=None)
    def test_receive_messages_uses_subscription_receiver(self, _sleep: MagicMock) -> None:
        message = create_message("1")
        self.sb_receiver.receive_messages.return_value = [message]

        self.client.receive_messages(1, lambda msg: True)

        self.service_bus_client.get_subscription_receiver.assert_called_once()
        self.sb_receiver.complete_message.assert_called_once_with(message)
        self.sb_receiver.abandon_message.assert_not_called()

    @patch("message_bus_lib.message_receiver_client.AutoLockRenewer")
    @patch("time.sleep", return_value=None)
    def test_autolock_renewer_closed_once_after_entire_batch(
        self, _sleep: MagicMock, mock_renewer_cls: MagicMock
    ) -> None:
        messages = [create_message("1"), create_message("2"), create_message("3")]
        self.sb_receiver.receive_messages.return_value = messages
        mock_renewer = MagicMock()
        mock_renewer_cls.return_value = mock_renewer

        self.client.receive_messages(3, lambda msg: True)

        self.assertEqual(self.sb_receiver.complete_message.call_count, 3)
        mock_renewer.close.assert_called_once()

    @patch("message_bus_lib.message_receiver_client.AutoLockRenewer")
    @patch("time.sleep", return_value=None)
    def test_autolock_renewer_closed_on_session_cannot_be_locked(
        self, _sleep: MagicMock, mock_renewer_cls: MagicMock
    ) -> None:
        mock_renewer = MagicMock()
        mock_renewer_cls.return_value = mock_renewer
        self.service_bus_client.get_subscription_receiver.return_value.__enter__.side_effect = SessionCannotBeLockedError()

        self.client.receive_messages(1, lambda msg: True)

        mock_renewer.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()