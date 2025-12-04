import unittest
from unittest.mock import MagicMock, Mock, patch

from azure.servicebus import ServiceBusMessage
from hl7apy.core import Message

from hl7_sender.app_config import AppConfig
from hl7_sender.application import _process_message, main


def _setup() -> tuple[ServiceBusMessage, Message, str, MagicMock, MagicMock, MagicMock, MagicMock]:
    hl7_message = Message("ADT_A01")
    hl7_message.msh.msh_10 = 'MSGID1234'
    hl7_string = hl7_message.to_er7()
    service_bus_message = ServiceBusMessage(body=hl7_string)
    mock_hl7_sender_client = MagicMock()
    mock_event_logger = MagicMock()
    mock_metric_sender = MagicMock()
    mock_throttler = MagicMock()

    return (
        service_bus_message, hl7_message, hl7_string, mock_hl7_sender_client,
        mock_event_logger, mock_metric_sender, mock_throttler
    )


class TestProcessMessage(unittest.TestCase):

    def _assert_error_handling(
        self,
        result: bool,
        mock_event_logger: MagicMock,
        mock_metric_sender: MagicMock,
    ) -> None:
        mock_event_logger.log_message_received.assert_called_once()
        mock_event_logger.log_message_failed.assert_called_once()
        mock_metric_sender.send_message_sent_metric.assert_not_called()
        self.assertFalse(result)

    @patch("hl7_sender.application.parse_message")
    @patch("hl7_sender.application.get_ack_result")
    def test_process_message_success(self, mock_ack_processor: Mock, mock_parse_message: Mock) -> None:
        # Arrange
        (
            service_bus_message,
            hl7_message,
            hl7_string,
            mock_hl7_sender_client,
            mock_event_logger,
            mock_metric_sender,
            mock_throttler,
        ) = _setup()
        mock_parse_message.return_value = hl7_message
        hl7_ack_message = "HL7 ack message"
        mock_hl7_sender_client.send_message.return_value = hl7_ack_message
        mock_ack_processor.return_value = True

        # Act
        result = _process_message(
            service_bus_message, mock_hl7_sender_client, mock_event_logger,
            mock_metric_sender, mock_throttler
        )

        # Assert
        mock_parse_message.assert_called_once_with(hl7_string)
        mock_ack_processor.assert_called_once_with(hl7_ack_message)
        mock_event_logger.log_message_received.assert_called_once()
        mock_event_logger.log_message_processed.assert_called_once()
        mock_metric_sender.send_message_sent_metric.assert_called_once()
        mock_throttler.wait_if_needed.assert_called_once()
        mock_throttler.record_message_sent.assert_called_once()

        self.assertTrue(result)

    @patch("hl7_sender.application.parse_message")
    @patch("hl7_sender.application.get_ack_result")
    def test_process_message_success_with_negative_ack(
        self, mock_ack_processor: Mock, mock_parse_message: Mock
    ) -> None:
        # Arrange
        (
            service_bus_message,
            hl7_message,
            hl7_string,
            mock_hl7_sender_client,
            mock_event_logger,
            mock_metric_sender,
            mock_throttler,
        ) = _setup()
        mock_parse_message.return_value = hl7_message
        hl7_ack_message = "HL7 ack message"
        mock_hl7_sender_client.send_message.return_value = hl7_ack_message
        mock_ack_processor.return_value = False  # Negative ACK

        # Act
        result = _process_message(
            service_bus_message, mock_hl7_sender_client, mock_event_logger,
            mock_metric_sender, mock_throttler
        )

        # Assert
        mock_parse_message.assert_called_once_with(hl7_string)
        mock_ack_processor.assert_called_once_with(hl7_ack_message)
        mock_event_logger.log_message_received.assert_called_once()
        mock_event_logger.log_message_processed.assert_called_once()
        mock_metric_sender.send_message_sent_metric.assert_not_called()
        mock_throttler.wait_if_needed.assert_called_once()
        mock_throttler.record_message_sent.assert_called_once()

        self.assertFalse(result)

    @patch("hl7_sender.application.parse_message")
    def test_process_message_send_errors(self, mock_parse_message: Mock) -> None:
        error_cases = [
            {"description": "timeout_error", "error": TimeoutError("No ACK received within 30 seconds")},
            {"description": "connection_error", "error": ConnectionError("Connection failed")},
        ]

        for case in error_cases:
            with self.subTest(error=case["description"]):
                # Arrange
                (
                    service_bus_message,
                    hl7_message,
                    hl7_string,
                    mock_hl7_sender_client,
                    mock_event_logger,
                    mock_metric_sender,
                    mock_throttler,
                ) = _setup()
                mock_parse_message.return_value = hl7_message
                mock_hl7_sender_client.send_message.side_effect = case["error"]

                # Act
                result = _process_message(
                    service_bus_message, mock_hl7_sender_client, mock_event_logger, mock_metric_sender, mock_throttler
                )

                # Assert
                self._assert_error_handling(result, mock_event_logger, mock_metric_sender)
                mock_throttler.wait_if_needed.assert_called_once()
                mock_throttler.record_message_sent.assert_called_once()

    @patch("hl7_sender.application.parse_message")
    def test_process_message_unexpected_error(self, mock_parse_message: Mock) -> None:
        # Arrange
        (
            service_bus_message,
            hl7_message,
            hl7_string,
            mock_hl7_sender_client,
            mock_event_logger,
            mock_metric_sender,
            mock_throttler,
        ) = _setup()
        mock_parse_message.side_effect = Exception("Unexpected error")

        # Act
        result = _process_message(
            service_bus_message, mock_hl7_sender_client, mock_event_logger,
            mock_metric_sender, mock_throttler
        )

        # Assert
        self._assert_error_handling(result, mock_event_logger, mock_metric_sender)
        mock_throttler.wait_if_needed.assert_not_called()
        mock_throttler.record_message_sent.assert_not_called()

    @patch("hl7_sender.application.ConnectionConfig")
    @patch("hl7_sender.application.ServiceBusClientFactory")
    @patch("hl7_sender.application.AppConfig")
    @patch("hl7_sender.application.TCPHealthCheckServer")
    @patch("hl7_sender.application.HL7SenderClient")
    @patch("hl7_sender.application.EventLogger")
    def test_health_check_server_starts_and_stops(
        self, mock_event_logger: Mock, mock_hl7_sender: Mock, mock_health_check: Mock,
            mock_app_config: Mock, mock_factory: Mock, mock_connection_config: Mock) -> None:
        # Arrange
        mock_health_server = MagicMock()
        mock_health_check_ctx = MagicMock()
        mock_health_check_ctx.__enter__.return_value = mock_health_server
        mock_health_check.return_value = mock_health_check_ctx
        mock_app_config.read_env_config.return_value = AppConfig(
            connection_string=None,
            ingress_queue_name="test-queue-name",
            ingress_session_id="test-session-id",
            service_bus_namespace=None,
            receiver_mllp_hostname="test-hostname",
            receiver_mllp_port=2575,
            health_check_hostname="localhost",
            health_check_port=9000,
            audit_queue_name="test_audit_queue",
            workflow_id="test_workflow_id",
            microservice_id="test_microservice_id",
            health_board="test-health-board",
            peer_service="test-service",
            ack_timeout_seconds=30,
            messages_per_minute=None
        )
        # Mock ProcessorManager to exit the loop immediately
        with patch("hl7_sender.application.ProcessorManager") as mock_processor_manager:
            mock_instance = mock_processor_manager.return_value
            mock_instance.is_running = False

            # Act
            main()

            # Assert
            mock_health_check.assert_called_once_with("localhost", 9000)
            mock_health_server.start.assert_called_once()
            mock_health_check_ctx.__exit__.assert_called_once()


if __name__ == '__main__':
    unittest.main()
