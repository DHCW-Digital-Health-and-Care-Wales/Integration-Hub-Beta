import unittest
from unittest.mock import MagicMock, patch

from message_bus_lib.connection_config import ConnectionConfig
from message_bus_lib.servicebus_client_factory import ServiceBusClientFactory


class TestServiceBusClientFactoryClose(unittest.TestCase):
    """Tests for close() and context manager on ServiceBusClientFactory."""

    @patch("message_bus_lib.servicebus_client_factory.ServiceBusClient")
    def test_close_closes_underlying_client(self, mock_sb_client_cls: MagicMock) -> None:
        mock_sb_client = MagicMock()
        mock_sb_client_cls.from_connection_string.return_value = mock_sb_client
        config = ConnectionConfig(connection_string="Endpoint=sb://test;", service_bus_namespace=None)

        factory = ServiceBusClientFactory(config)
        factory.close()

        mock_sb_client.close.assert_called_once()

    @patch("message_bus_lib.servicebus_client_factory.ServiceBusClient")
    def test_context_manager_closes_on_exit(self, mock_sb_client_cls: MagicMock) -> None:
        mock_sb_client = MagicMock()
        mock_sb_client_cls.from_connection_string.return_value = mock_sb_client
        config = ConnectionConfig(connection_string="Endpoint=sb://test;", service_bus_namespace=None)

        with ServiceBusClientFactory(config) as factory:
            self.assertIsInstance(factory, ServiceBusClientFactory)

        mock_sb_client.close.assert_called_once()

    @patch("message_bus_lib.servicebus_client_factory.ServiceBusClient")
    def test_context_manager_closes_on_exception(self, mock_sb_client_cls: MagicMock) -> None:
        mock_sb_client = MagicMock()
        mock_sb_client_cls.from_connection_string.return_value = mock_sb_client
        config = ConnectionConfig(connection_string="Endpoint=sb://test;", service_bus_namespace=None)

        with self.assertRaises(RuntimeError):
            with ServiceBusClientFactory(config):
                raise RuntimeError("boom")

        mock_sb_client.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
