import unittest
from unittest.mock import MagicMock, PropertyMock, patch

from message_store_service.message_store_service import MessageStoreService


class TestMessageStoreServiceInit(unittest.TestCase):
    """Tests for MessageStoreService.__init__ — verify config and DatabaseClient creation."""

    @patch("message_store_service.message_store_service.DatabaseClient")
    @patch("message_store_service.message_store_service.AppConfig.read_env_config")
    @patch("message_store_service.message_store_service.ProcessorManager")
    def test_initialization_creates_db_client(
        self,
        mock_processor_manager: MagicMock,
        mock_read_env_config: MagicMock,
        mock_db_client_cls: MagicMock,
    ) -> None:
        # Arrange
        mock_config = MagicMock()
        mock_config.sql_server = "localhost,1433"
        mock_config.sql_database = "IntegrationHub"
        mock_config.sql_username = "sa"
        mock_config.sql_password = "secret"  # nosec B105 — test fixture, not real password
        mock_config.sql_encrypt = "yes"
        mock_config.sql_trust_server_certificate = "yes"
        mock_config.managed_identity_client_id = None
        mock_read_env_config.return_value = mock_config

        # Act
        service = MessageStoreService(batch_size=100)

        # Assert
        mock_read_env_config.assert_called_once()
        self.assertEqual(service.config, mock_config)
        self.assertEqual(service.batch_size, 100)
        mock_processor_manager.assert_called_once()
        mock_db_client_cls.assert_called_once_with(
            sql_server="localhost,1433",
            sql_database="IntegrationHub",
            sql_username="sa",
            sql_password="secret",  # nosec B106 — test fixture, not real password
            sql_encrypt="yes",
            sql_trust_server_certificate="yes",
            managed_identity_client_id=None,
        )


class TestMessageStoreServiceRun(unittest.TestCase):
    """Tests for MessageStoreService.run — verify service wiring."""

    @patch("message_store_service.message_store_service.DatabaseClient")
    @patch("message_store_service.message_store_service.AppConfig.read_env_config")
    @patch("message_store_service.message_store_service.ProcessorManager")
    @patch("message_store_service.message_store_service.ServiceBusClientFactory")
    @patch("message_store_service.message_store_service.EventLogger")
    @patch("message_store_service.message_store_service.TCPHealthCheckServer")
    def test_run_starts_service_and_enters_context_managers(
        self,
        mock_health_check: MagicMock,
        mock_event_logger: MagicMock,
        mock_factory_class: MagicMock,
        mock_processor_manager: MagicMock,
        mock_read_env_config: MagicMock,
        mock_db_client_cls: MagicMock,
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

        # Setup db_client context manager
        mock_db_client = MagicMock()
        mock_db_client_cls.return_value = mock_db_client
        mock_db_client.__enter__ = MagicMock(return_value=mock_db_client)
        mock_db_client.__exit__ = MagicMock(return_value=None)

        # Act
        service = MessageStoreService(batch_size=100)
        service.run()

        # Assert
        mock_factory_class.assert_called_once()
        call_args = mock_factory_class.call_args[0]
        self.assertEqual(call_args[0].connection_string, "test_conn_str")
        self.assertEqual(call_args[0].service_bus_namespace, "test_namespace")

        mock_event_logger.assert_called_once_with(
            workflow_id="message_store",
            microservice_id="service_1"
        )
        mock_health_check.assert_called_once()
        mock_factory.create_message_receiver_client.assert_called_once_with(
            queue_name="test_queue",
            session_id=None
        )


class TestProcessMessages(unittest.TestCase):
    """Tests for MessageStoreService._process_messages — batch flow with callback."""

    @patch("message_store_service.message_store_service.DatabaseClient")
    @patch("message_store_service.message_store_service.AppConfig.read_env_config")
    @patch("message_store_service.message_store_service.ProcessorManager")
    @patch("message_store_service.message_store_service.build_message_records")
    def test_process_messages_stores_and_completes_batch(
        self,
        mock_build_records: MagicMock,
        mock_processor_manager: MagicMock,
        mock_read_env_config: MagicMock,
        mock_db_client_cls: MagicMock,
    ) -> None:
        """On a successful batch, store_messages is called and callback returns True (messages completed)."""
        # Arrange
        mock_config = MagicMock()
        mock_config.microservice_id = "svc"
        mock_read_env_config.return_value = mock_config

        mock_proc_mgr = MagicMock()
        # Run one iteration then stop
        type(mock_proc_mgr).is_running = PropertyMock(side_effect=[True, False])
        mock_processor_manager.return_value = mock_proc_mgr

        mock_db_client = MagicMock()
        mock_db_client_cls.return_value = mock_db_client

        mock_receiver = MagicMock()
        # Capture the callback so we can invoke it
        captured_callback = None

        batch_processor_result = None

        def capture_receive_messages_batch(num_of_messages: int, batch_processor) -> None:  # type: ignore[no-untyped-def]
            nonlocal captured_callback, batch_processor_result
            captured_callback = batch_processor
            # Simulate one batch received
            messages = [MagicMock(), MagicMock()]
            batch_processor_result = batch_processor(messages)

        mock_receiver.receive_messages_batch = capture_receive_messages_batch

        mock_records = [MagicMock(), MagicMock()]
        mock_build_records.return_value = mock_records

        mock_event_logger = MagicMock()

        # Act
        service = MessageStoreService(batch_size=50)
        service._process_messages(mock_receiver, mock_event_logger)

        # Assert
        self.assertIsNotNone(captured_callback)
        self.assertTrue(batch_processor_result)
        mock_build_records.assert_called_once()
        mock_db_client.store_messages.assert_called_once_with(mock_records)

    @patch("message_store_service.message_store_service.DatabaseClient")
    @patch("message_store_service.message_store_service.AppConfig.read_env_config")
    @patch("message_store_service.message_store_service.ProcessorManager")
    @patch("message_store_service.message_store_service.build_message_records")
    def test_process_messages_abandons_batch_on_db_error(
        self,
        mock_build_records: MagicMock,
        mock_processor_manager: MagicMock,
        mock_read_env_config: MagicMock,
        mock_db_client_cls: MagicMock,
    ) -> None:
        """On a DB failure, callback returns False and messages are abandoned."""
        mock_config = MagicMock()
        mock_config.microservice_id = "svc"
        mock_read_env_config.return_value = mock_config

        mock_proc_mgr = MagicMock()
        type(mock_proc_mgr).is_running = PropertyMock(side_effect=[True, False])
        mock_processor_manager.return_value = mock_proc_mgr

        mock_db_client = MagicMock()
        mock_db_client.store_messages.side_effect = Exception("DB error")
        mock_db_client_cls.return_value = mock_db_client

        mock_receiver = MagicMock()

        def simulate_batch(num_of_messages: int, batch_processor) -> None:  # type: ignore[no-untyped-def]
            result = batch_processor([MagicMock()])
            # Should return False due to exception
            self.assertFalse(result)

        mock_receiver.receive_messages_batch = simulate_batch

        mock_build_records.return_value = [MagicMock()]
        mock_event_logger = MagicMock()

        # Act
        service = MessageStoreService(batch_size=50)
        service._process_messages(mock_receiver, mock_event_logger)

        # Assert
        mock_event_logger.log_message_failed.assert_called_once()

    @patch("message_store_service.message_store_service.DatabaseClient")
    @patch("message_store_service.message_store_service.AppConfig.read_env_config")
    @patch("message_store_service.message_store_service.ProcessorManager")
    def test_process_messages_skips_empty_batch(
        self,
        mock_processor_manager: MagicMock,
        mock_read_env_config: MagicMock,
        mock_db_client_cls: MagicMock,
    ) -> None:
        """When receive_messages_batch gets no messages, callback is not invoked."""
        mock_config = MagicMock()
        mock_read_env_config.return_value = mock_config

        mock_proc_mgr = MagicMock()
        type(mock_proc_mgr).is_running = PropertyMock(side_effect=[True, False])
        mock_processor_manager.return_value = mock_proc_mgr

        mock_db_client = MagicMock()
        mock_db_client_cls.return_value = mock_db_client

        mock_receiver = MagicMock()
        # Simulate no messages — callback not invoked
        mock_receiver.receive_messages_batch = MagicMock()

        mock_event_logger = MagicMock()

        # Act
        service = MessageStoreService(batch_size=50)
        service._process_messages(mock_receiver, mock_event_logger)

        # Assert
        mock_db_client.store_messages.assert_not_called()


if __name__ == "__main__":
    unittest.main()



