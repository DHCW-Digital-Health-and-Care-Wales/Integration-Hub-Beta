import os
import unittest
from unittest.mock import MagicMock, patch

from message_bus_lib.connection_config import ConnectionConfig
from message_bus_lib.message_store_client import MessageStoreClient
from message_bus_lib.servicebus_client_factory import ServiceBusClientFactory


def _make_factory() -> ServiceBusClientFactory:
    """Return a factory instance with a mocked underlying ServiceBusClient."""
    config = ConnectionConfig(
        connection_string="Endpoint=sb://localhost;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=abc123",
        service_bus_namespace=None,
    )
    with patch("message_bus_lib.servicebus_client_factory.ServiceBusClient") as mock_sb_cls:
        mock_sb_cls.from_connection_string.return_value = MagicMock()
        factory = ServiceBusClientFactory(config)
    # Replace the internal servicebus_client with a fresh mock so queue-sender calls are tracked.
    factory.servicebus_client = MagicMock()  # type: ignore[assignment]
    return factory

class TestServiceBusClientFactoryClose(unittest.TestCase):
    """Tests for close() and context manager on ServiceBusClientFactory."""

    def setUp(self) -> None:
        self.factory = _make_factory()
        self.mock_sb_client: MagicMock = self.factory.servicebus_client  # type: ignore[assignment]

    def test_close_closes_underlying_client(self) -> None:
        self.factory.close()

        self.mock_sb_client.close.assert_called_once()

    def test_context_manager_closes_on_exit(self) -> None:
        with self.factory as f:
            self.assertIsInstance(f, ServiceBusClientFactory)

        self.mock_sb_client.close.assert_called_once()

    def test_context_manager_closes_on_exception(self) -> None:
        with self.assertRaises(RuntimeError):
            with self.factory:
                raise RuntimeError("boom")

        self.mock_sb_client.close.assert_called_once()

class TestCreateMessageStoreClient(unittest.TestCase):
    """Tests for ServiceBusClientFactory.create_message_store_client."""

    def setUp(self) -> None:
        self.factory = _make_factory()
        # Capture as MagicMock so mypy can resolve assert_* methods on it.
        self.mock_sb_client: MagicMock = self.factory.servicebus_client  # type: ignore[assignment]

    @patch.dict(os.environ, {"MESSAGE_STORE_ENABLED": "true"})
    def test_create_message_store_client_enabled(self) -> None:
        """When MESSAGE_STORE_ENABLED=true a live sender is created and returned inside the client."""
        with patch.object(self.factory, "logger") as mock_logger:
            client = self.factory.create_message_store_client("store-queue", "svc-id", "peer-svc")

        self.assertIsInstance(client, MessageStoreClient)
        self.assertIsNotNone(client.sender_client)
        # The underlying Service Bus get_queue_sender should have been called once for the store queue.
        self.mock_sb_client.get_queue_sender.assert_called_once_with(queue_name="store-queue")
        mock_logger.info.assert_called_with(
            "Message store is enabled — configured queue: %s", "store-queue"
        )

    @patch.dict(os.environ, {"MESSAGE_STORE_ENABLED": "false"})
    def test_create_message_store_client_disabled(self) -> None:
        """When MESSAGE_STORE_ENABLED=false no sender is created and sender_client is None."""
        client = self.factory.create_message_store_client("store-queue", "svc-id", "peer-svc")

        self.assertIsInstance(client, MessageStoreClient)
        self.assertIsNone(client.sender_client)
        # No Service Bus sender should be opened when disabled.
        self.mock_sb_client.get_queue_sender.assert_not_called()

    @patch.dict(os.environ, {"MESSAGE_STORE_ENABLED": "FALSE"})
    def test_create_message_store_client_disabled_case_insensitive(self) -> None:
        """MESSAGE_STORE_ENABLED=FALSE (uppercase) is treated as disabled."""
        client = self.factory.create_message_store_client("store-queue", "svc-id", "peer-svc")

        self.assertIsNone(client.sender_client)
        self.mock_sb_client.get_queue_sender.assert_not_called()

    def test_create_message_store_client_enabled_by_default(self) -> None:
        """When MESSAGE_STORE_ENABLED is absent the message store is enabled by default."""
        env = {k: v for k, v in os.environ.items() if k != "MESSAGE_STORE_ENABLED"}
        with patch.dict(os.environ, env, clear=True):
            client = self.factory.create_message_store_client("store-queue", "svc-id", "peer-svc")

        self.assertIsNotNone(client.sender_client)
        self.mock_sb_client.get_queue_sender.assert_called_once_with(queue_name="store-queue")

    @patch.dict(os.environ, {"MESSAGE_STORE_ENABLED": "true"})
    def test_create_message_store_client_propagates_identifiers(self) -> None:
        """microservice_id and peer_service are forwarded to the MessageStoreClient."""
        client = self.factory.create_message_store_client("store-queue", "my-service", "my-peer")

        self.assertEqual(client.microservice_id, "my-service")
        self.assertEqual(client.peer_service, "my-peer")

    @patch.dict(os.environ, {"MESSAGE_STORE_ENABLED": "false"})
    def test_create_message_store_client_disabled_logs_warning(self) -> None:
        """A warning is emitted at startup when the message store is disabled."""
        with patch.object(self.factory, "logger") as mock_logger:
            self.factory.create_message_store_client("store-queue", "svc-id", "peer-svc")

        mock_logger.warning.assert_called_with(
            "Message store is disabled — no sender client will be created."
        )

if __name__ == "__main__":
    unittest.main()
