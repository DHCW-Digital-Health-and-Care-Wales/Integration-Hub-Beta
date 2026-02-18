import unittest
from unittest.mock import MagicMock, patch

from message_store_service.message_store_service import MessageStoreService


class TestMessageStoreService(unittest.TestCase):
    @patch("message_store_service.message_store_service.AppConfig.read_env_config")
    @patch("message_store_service.message_store_service.ProcessorManager")
    def test_message_store_service_initialization(
        self,
        mock_processor_manager: MagicMock,
        mock_read_env_config: MagicMock
    ) -> None:
        # Arrange
        mock_config = MagicMock()
        mock_read_env_config.return_value = mock_config
        batch_size = 100

        # Act
        service = MessageStoreService(batch_size)

        # Assert
        mock_read_env_config.assert_called_once()
        self.assertEqual(service.config, mock_config)
        self.assertEqual(service.batch_size, batch_size)
        mock_processor_manager.assert_called_once()

    @patch("message_store_service.message_store_service.AppConfig.read_env_config")
    @patch("message_store_service.message_store_service.ProcessorManager")
    @patch("message_store_service.message_store_service.ServiceBusClientFactory")
    @patch("message_store_service.message_store_service.EventLogger")
    @patch("message_store_service.message_store_service.TCPHealthCheckServer")
    def test_run_starts_service_and_processes_messages(
        self,
        mock_health_check: MagicMock,
        mock_event_logger: MagicMock,
        mock_factory_class: MagicMock,
        mock_processor_manager: MagicMock,
        mock_read_env_config: MagicMock
    ) -> None:
        # Arrange
        mock_config = MagicMock()
        mock_config.connection_string = "test_conn_str"
        mock_config.service_bus_namespace = "test_namespace"
        mock_config.ingress_queue_name = "test_queue"
        mock_config.microservice_id = "service_1"
        mock_read_env_config.return_value = mock_config

        # Setup processor manager to stop immediately
        mock_proc_mgr = MagicMock()
        mock_proc_mgr.is_running = False
        mock_processor_manager.return_value = mock_proc_mgr

        # Setup health check server context manager
        mock_health_server = MagicMock()
        mock_health_check.return_value.__enter__ = MagicMock(return_value=mock_health_server)
        mock_health_check.return_value.__exit__ = MagicMock(return_value=None)

        # Setup factory and receiver
        mock_factory = MagicMock()
        mock_factory_class.return_value = mock_factory
        mock_receiver = MagicMock()
        receiver_ctx_mgr = MagicMock()
        receiver_ctx_mgr.__enter__ = MagicMock(return_value=mock_receiver)
        receiver_ctx_mgr.__exit__ = MagicMock(return_value=None)
        mock_factory.create_message_receiver_client.return_value = receiver_ctx_mgr

        # Act
        service = MessageStoreService(batch_size=100)
        service.run()

        # Assert
        # Verify ConnectionConfig was passed to factory
        mock_factory_class.assert_called_once()
        call_args = mock_factory_class.call_args[0]
        self.assertEqual(call_args[0].connection_string, "test_conn_str")
        self.assertEqual(call_args[0].service_bus_namespace, "test_namespace")

        # Verify EventLogger was created with hardcoded workflow_id
        mock_event_logger.assert_called_once_with(
            workflow_id="message_store",
            microservice_id="service_1"
        )
        mock_health_check.assert_called_once()
        mock_factory.create_message_receiver_client.assert_called_once_with(
            queue_name="test_queue",
            session_id=None
        )


if __name__ == "__main__":
    unittest.main()



