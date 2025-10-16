import unittest
from unittest.mock import MagicMock, patch

from azure.servicebus import ServiceBusMessage
from hl7apy.core import Message
from transformer_base_lib.app_config import AppConfig as BaseAppConfig
from transformer_base_lib.message_processor import process_message

from hl7_phw_transformer.application import main
from hl7_phw_transformer.phw_transformer import PhwTransformer


class TestProcessPhwMessage(unittest.TestCase):
    def setUp(self) -> None:
        self.created_datetime = "2025-05-22_10:30:00"
        self.resurrec_dod = "RESURREC"
        self.hl7_message = Message("ADT_A01")
        self.hl7_message.msh.msh_7 = self.created_datetime
        self.hl7_message.msh.msh_10 = "MSGID1234"
        self.hl7_message.pid.pid_29 = self.resurrec_dod

        self.hl7_string = self.hl7_message.to_er7()
        self.service_bus_message = ServiceBusMessage(body=self.hl7_string)

        self.transformer = PhwTransformer()
        self.mock_sender = MagicMock()
        self.mock_event_logger = MagicMock()

        self.process_message_kwargs = {
            "sender_client": self.mock_sender,
            "event_logger": self.mock_event_logger,
            "transform": self.transformer.transform_message,
            "transformer_display_name": "PHW",
            "received_audit_text": self.transformer.get_received_audit_text(),
            "processed_audit_text_builder": self.transformer.get_processed_audit_text,
            "failed_audit_text": "PHW transformation failed",
        }

    @patch("hl7_phw_transformer.phw_transformer.transform_datetime")
    @patch("hl7_phw_transformer.phw_transformer.transform_date_of_death")
    def test_process_message_success(
        self,
        mock_transform_dod: MagicMock,
        mock_transform_datetime: MagicMock
    ) -> None:
        # Arrange
        mock_transform_datetime.return_value = "20250522103000"
        mock_transform_dod.return_value = '""'

        # Act
        result = process_message(self.service_bus_message, **self.process_message_kwargs)

        # Assert
        mock_transform_datetime.assert_called_once_with(self.created_datetime)
        mock_transform_dod.assert_called_once_with(self.resurrec_dod)
        self.assertTrue(result)

        # Check that the transformed message was sent
        self.mock_sender.send_message.assert_called_once()

        # Verify audit logging
        self.mock_event_logger.log_message_received.assert_called_once_with(
            self.hl7_string, "Message received for PHW transformation"
        )
        audit_message = (
            "HL7 transformations applied: DateTime transformed from 2025-05-22_10:30:00 to 20250522103000; "
            'Date of death transformed from RESURREC to ""'
        )
        self.mock_event_logger.log_message_processed.assert_called_once_with(
            self.hl7_string,
            audit_message,
        )

    @patch("hl7_phw_transformer.phw_transformer.transform_datetime")
    @patch("hl7_phw_transformer.phw_transformer.transform_date_of_death")
    def test_process_message_with_valid_date_of_death(
        self,
        mock_transform_dod: MagicMock,
        mock_transform_datetime: MagicMock
    ) -> None:
        # Arrange
        created_datetime = "2025-05-22 10:30:00"
        valid_dod = "2023-01-15"
        hl7_message = Message("ADT_A01")
        hl7_message.msh.msh_7 = created_datetime
        hl7_message.msh.msh_10 = "MSGID1234"
        hl7_message.pid.pid_29 = valid_dod

        hl7_string = hl7_message.to_er7()
        service_bus_message = ServiceBusMessage(body=hl7_string)

        mock_transform_datetime.return_value = "20250522103000"
        mock_transform_dod.return_value = valid_dod  # No change needed

        process_message_kwargs = {
            "sender_client": self.mock_sender,
            "event_logger": self.mock_event_logger,
            "transform": self.transformer.transform_message,
            "transformer_display_name": "PHW",
            "received_audit_text": self.transformer.get_received_audit_text(),
            "processed_audit_text_builder": self.transformer.get_processed_audit_text,
            "failed_audit_text": "PHW transformation failed",
        }

        # Act
        result = process_message(service_bus_message, **process_message_kwargs)

        # Assert
        mock_transform_dod.assert_called_once_with(valid_dod)
        self.assertTrue(result)

    @patch("hl7_phw_transformer.phw_transformer.transform_datetime")
    def test_process_message_failure_due_to_transform(
        self,
        mock_transform_datetime: MagicMock
    ) -> None:
        # Arrange
        created_datetime = "invalid_datetime"
        hl7_message = Message("ADT_A01")
        hl7_message.msh.msh_7 = created_datetime
        hl7_message.msh.msh_10 = "MSGID1234"

        hl7_string = hl7_message.to_er7()
        service_bus_message = ServiceBusMessage(body=hl7_string)

        error_reason = "Invalid date"
        mock_transform_datetime.side_effect = ValueError(error_reason)

        process_message_kwargs = {
            "sender_client": self.mock_sender,
            "event_logger": self.mock_event_logger,
            "transform": self.transformer.transform_message,
            "transformer_display_name": "PHW",
            "received_audit_text": self.transformer.get_received_audit_text(),
            "processed_audit_text_builder": self.transformer.get_processed_audit_text,
            "failed_audit_text": "PHW transformation failed",
        }

        # Act
        result = process_message(service_bus_message, **process_message_kwargs)

        # Assert
        mock_transform_datetime.assert_called_once_with(created_datetime)
        self.mock_sender.send_message.assert_not_called()

        self.mock_event_logger.log_message_received.assert_called_once_with(
            hl7_string, "Message received for PHW transformation"
        )
        self.mock_event_logger.log_message_failed.assert_called_once_with(
            hl7_string,
            f"Failed to transform PHW message: {error_reason}",
            "PHW transformation failed",
        )
        self.mock_event_logger.log_message_processed.assert_not_called()

        self.assertFalse(result)

    @patch("hl7_phw_transformer.application.EventLogger")
    @patch("transformer_base_lib.app_config.AppConfig.read_env_config")
    @patch("transformer_base_lib.run_transformer.ServiceBusClientFactory")
    @patch("transformer_base_lib.run_transformer.TCPHealthCheckServer")
    def test_health_check_server_starts_and_stops(
        self,
        mock_health_check: MagicMock,
        mock_factory: MagicMock,
        mock_read_env_config: MagicMock,
        mock_event_logger: MagicMock
    ) -> None:
        # Arrange
        # Create proper context manager mocks for all clients
        mock_health_server = MagicMock()
        mock_health_check.return_value.__enter__ = MagicMock(return_value=mock_health_server)
        mock_health_check.return_value.__exit__ = MagicMock(return_value=None)

        # Mock sender and receiver clients context managers
        mock_sender_client = MagicMock()
        mock_receiver_client = MagicMock()
        mock_factory_instance = MagicMock()
        mock_factory.return_value = mock_factory_instance
        sender_ctx_mgr = MagicMock()
        sender_ctx_mgr.__enter__ = MagicMock(return_value=mock_sender_client)
        sender_ctx_mgr.__exit__ = MagicMock(return_value=None)
        mock_factory_instance.create_queue_sender_client.return_value = sender_ctx_mgr
        receiver_ctx_mgr = MagicMock()
        receiver_ctx_mgr.__enter__ = MagicMock(return_value=mock_receiver_client)
        receiver_ctx_mgr.__exit__ = MagicMock(return_value=None)
        mock_factory_instance.create_message_receiver_client.return_value = receiver_ctx_mgr
        mock_receiver_client.receive_messages = MagicMock()

        # Mock the base AppConfig to return proper values
        mock_read_env_config.return_value = BaseAppConfig(
            connection_string="connection_string",
            ingress_queue_name="ingress_queue",
            ingress_session_id=None,
            egress_queue_name="egress_queue",
            egress_session_id=None,
            service_bus_namespace="service_bus_namespace",
            audit_queue_name=None,
            workflow_id="workflow_id",
            microservice_id="microservice_id",
            health_check_hostname="localhost",
            health_check_port=9000,
        )

        # Mock ProcessorManager to exit the loop immediately
        with patch("transformer_base_lib.run_transformer.ProcessorManager") as mock_processor_manager:
            mock_instance = mock_processor_manager.return_value
            mock_instance.is_running = False

            # Act
            main()

            # Assert
            mock_health_check.assert_called_once_with("localhost", 9000)
            mock_health_server.start.assert_called_once()
            mock_health_check.return_value.__exit__.assert_called_once()


if __name__ == "__main__":
    unittest.main()
