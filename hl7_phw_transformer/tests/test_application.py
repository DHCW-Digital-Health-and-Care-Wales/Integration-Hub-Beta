import unittest
from typing import Optional, Tuple
from unittest.mock import MagicMock, patch

from azure.servicebus import ServiceBusMessage
from hl7apy.core import Message

from hl7_phw_transformer.app_config import AppConfig
from hl7_phw_transformer.application import _process_message, main


def _setup(
    created_datetime: str, date_of_death: Optional[str] = None
) -> Tuple[ServiceBusMessage, Message, str, MagicMock, MagicMock]:
    hl7_message = Message("ADT_A01")
    hl7_message.msh.msh_7 = created_datetime
    hl7_message.msh.msh_10 = "MSGID1234"

    if date_of_death is not None:
        hl7_message.pid.pid_29 = date_of_death

    hl7_string = hl7_message.to_er7()
    service_bus_message = ServiceBusMessage(body=hl7_string)
    mock_sender = MagicMock()
    mock_event_logger = MagicMock()

    return service_bus_message, hl7_message, hl7_string, mock_sender, mock_event_logger


class TestProcessMessage(unittest.TestCase):
    @patch("hl7_phw_transformer.application.parse_message")
    @patch("hl7_phw_transformer.application.transform_datetime")
    @patch("hl7_phw_transformer.application.transform_date_of_death")
    def test_process_message_success(
        self,
        mock_transform_dod: MagicMock,
        mock_transform_datetime: MagicMock,
        mock_parse_message: MagicMock
    ) -> None:
        # Arrange
        created_datetime = "2025-05-22_10:30:00"
        resurrec_dod = "RESURREC"
        (
            service_bus_message,
            hl7_message,
            hl7_string,
            mock_sender,
            mock_event_logger,
        ) = _setup(created_datetime, resurrec_dod)
        mock_parse_message.return_value = hl7_message
        mock_transform_datetime.return_value = "20250522103000"
        mock_transform_dod.return_value = '""'

        # Act
        result = _process_message(service_bus_message, mock_sender, mock_event_logger)

        # Assert
        mock_parse_message.assert_called_once_with(hl7_string)
        mock_transform_datetime.assert_called_once_with(created_datetime)
        mock_transform_dod.assert_called_once_with(resurrec_dod)
        mock_sender.send_message.assert_called_once_with(hl7_message.to_er7())

        mock_event_logger.log_message_received.assert_called_once_with(
            hl7_string, "Message received for transformation"
        )
        audit_message = (
            "HL7 transformations applied: DateTime transformed from 2025-05-22_10:30:00 to 20250522103000; "
            'Date of death transformed from RESURREC to ""'
        )
        mock_event_logger.log_message_processed.assert_called_once_with(
            hl7_string,
            audit_message,
        )

        self.assertTrue(result)

    @patch("hl7_phw_transformer.application.parse_message")
    @patch("hl7_phw_transformer.application.transform_datetime")
    @patch("hl7_phw_transformer.application.transform_date_of_death")
    def test_process_message_with_valid_date_of_death(
        self,
        mock_transform_dod: MagicMock,
        mock_transform_datetime: MagicMock,
        mock_parse_message: MagicMock
    ) -> None:
        # Arrange
        created_datetime = "2025-05-22 10:30:00"
        valid_dod = "2023-01-15"
        service_bus_message, hl7_message, hl7_string, mock_sender, mock_event_logger = _setup(
            created_datetime, valid_dod
        )

        mock_parse_message.return_value = hl7_message
        mock_transform_datetime.return_value = "20250522103000"
        mock_transform_dod.return_value = valid_dod  # No change needed

        # Act
        result = _process_message(service_bus_message, mock_sender, mock_event_logger)

        # Assert
        mock_transform_dod.assert_called_once_with(valid_dod)
        self.assertTrue(result)

    @patch("hl7_phw_transformer.application.parse_message")
    @patch("hl7_phw_transformer.application.transform_datetime")
    def test_process_message_failure_due_to_transform(
        self,
        mock_transform_datetime: MagicMock,
        mock_parse_message: MagicMock
    ) -> None:
        # Arrange
        created_datetime = "invalid_datetime"
        service_bus_message, hl7_message, hl7_string, mock_sender, mock_event_logger = _setup(created_datetime)
        mock_parse_message.return_value = hl7_message
        error_reason = "Invalid date"
        mock_transform_datetime.side_effect = ValueError(error_reason)

        # Act
        result = _process_message(service_bus_message, mock_sender, mock_event_logger)

        # Assert
        mock_parse_message.assert_called_once_with(hl7_string)
        mock_transform_datetime.assert_called_once_with(created_datetime)
        mock_sender.send_message.assert_not_called()

        mock_event_logger.log_message_received.assert_called_once_with(
            hl7_string, "Message received for transformation"
        )
        mock_event_logger.log_message_failed.assert_called_once_with(
            hl7_string,
            f"Failed to transform datetime: {error_reason}",
            "DateTime transformation failed",
        )
        mock_event_logger.log_message_processed.assert_not_called()

        self.assertFalse(result)

    @patch("hl7_phw_transformer.application.EventLogger")
    @patch("hl7_phw_transformer.application.AppConfig")
    @patch("hl7_phw_transformer.application.ServiceBusClientFactory")
    @patch("hl7_phw_transformer.application.TCPHealthCheckServer")
    def test_health_check_server_starts_and_stops(
        self,
        mock_health_check: MagicMock,
        mock_factory: MagicMock,
        mock_app_config: MagicMock,
        mock_event_logger: MagicMock
    ) -> None:
        # Arrange
        mock_health_server = MagicMock()
        mock_health_check_ctx = MagicMock()
        mock_health_check_ctx.__enter__.return_value = mock_health_server
        mock_health_check.return_value = mock_health_check_ctx
        mock_app_config.read_env_config.return_value = AppConfig(
            None, "ingress_queue", None, "egress_queue", None, None, None, "workflow_id", "microservice_id",
            health_check_hostname="localhost",
            health_check_port=9000,
        )

        # Mock ProcessorManager to exit the loop immediately
        with patch("hl7_phw_transformer.application.ProcessorManager") as mock_processor_manager:
            mock_instance = mock_processor_manager.return_value
            mock_instance.is_running = False

            # Act
            main()

            # Assert
            mock_health_check.assert_called_once_with("localhost", 9000)
            mock_health_server.start.assert_called_once()
            mock_health_check_ctx.__exit__.assert_called_once()


if __name__ == "__main__":
    unittest.main()
