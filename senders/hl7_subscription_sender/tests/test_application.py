import unittest
from unittest.mock import MagicMock, Mock, patch

from azure.servicebus import ServiceBusMessage  # type: ignore
from hl7apy.core import Message  # type: ignore
from message_bus_lib.dead_letter import DeadLetterMessage

from hl7_subscription_sender.ack_processor import AckOutcome, AckResult
from hl7_subscription_sender.app_config import AppConfig
from hl7_subscription_sender.application import (
    MAX_BATCH_SIZE,
    _calculate_batch_size,
    _process_message,
    main,
)


def _setup() -> tuple[ServiceBusMessage, Message, str, MagicMock, MagicMock, MagicMock, MagicMock]:
    hl7_message = Message("ADT_A01")
    hl7_message.msh.msh_10 = "MSGID1234"
    hl7_string = hl7_message.to_er7()
    service_bus_message = ServiceBusMessage(body=hl7_string)
    mock_hl7_subscription_sender_client = MagicMock()
    mock_event_logger = MagicMock()
    mock_metric_sender = MagicMock()
    mock_throttler = MagicMock()

    return (
        service_bus_message,
        hl7_message,
        hl7_string,
        mock_hl7_subscription_sender_client,
        mock_event_logger,
        mock_metric_sender,
        mock_throttler,
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

    @patch("hl7_subscription_sender.application.parse_message")
    @patch("hl7_subscription_sender.application.get_ack_result")
    def test_process_message_success(self, mock_ack_processor: Mock, mock_parse_message: Mock) -> None:
        (
            service_bus_message,
            hl7_message,
            hl7_string,
            mock_hl7_subscription_sender_client,
            mock_event_logger,
            mock_metric_sender,
            mock_throttler,
        ) = _setup()
        mock_parse_message.return_value = hl7_message
        hl7_ack_message = "HL7 ack message"
        mock_hl7_subscription_sender_client.send_message.return_value = hl7_ack_message
        mock_ack_processor.return_value = AckResult(AckOutcome.SUCCESS, "AA", "MSGID1234", hl7_ack_message)

        result = _process_message(
            service_bus_message,
            mock_hl7_subscription_sender_client,
            mock_event_logger,
            mock_metric_sender,
            mock_throttler,
        )

        mock_parse_message.assert_called_once_with(hl7_string)
        mock_ack_processor.assert_called_once_with(hl7_ack_message)
        mock_event_logger.log_message_received.assert_called_once()
        mock_event_logger.log_message_processed.assert_called_once()
        mock_event_logger.log_message_failed.assert_not_called()
        mock_metric_sender.send_message_sent_metric.assert_called_once()

        # Preserve normal behaviour for AA: none of the NACK retry/escalation flow is triggered.
        mock_metric_sender.send_message_nack_ae_metric.assert_not_called()
        mock_metric_sender.send_message_nack_ar_metric.assert_not_called()
        mock_metric_sender.send_message_retry_attempt_metric.assert_not_called()
        mock_throttler.wait_if_needed.assert_called_once()

        self.assertTrue(result)

    @patch("hl7_subscription_sender.application.parse_message")
    @patch("hl7_subscription_sender.application.get_ack_result")
    def test_process_message_success_with_negative_ack(
        self, mock_ack_processor: Mock, mock_parse_message: Mock
    ) -> None:
        (
            service_bus_message,
            hl7_message,
            hl7_string,
            mock_hl7_subscription_sender_client,
            mock_event_logger,
            mock_metric_sender,
            mock_throttler,
        ) = _setup()
        mock_parse_message.return_value = hl7_message
        hl7_ack_message = "HL7 ack message"
        mock_hl7_subscription_sender_client.send_message.return_value = hl7_ack_message
        mock_hl7_subscription_sender_client.receiver_mllp_hostname = "mpi.example.org"
        mock_hl7_subscription_sender_client.receiver_mllp_port = 2575
        mock_ack_processor.return_value = AckResult(AckOutcome.AE, "AE", "MSGID1234", hl7_ack_message)

        result = _process_message(
            service_bus_message,
            mock_hl7_subscription_sender_client,
            mock_event_logger,
            mock_metric_sender,
            mock_throttler,
        )

        mock_parse_message.assert_called_once_with(hl7_string)
        mock_ack_processor.assert_called_once_with(hl7_ack_message)
        mock_event_logger.log_message_received.assert_called_once()
        mock_event_logger.log_message_failed.assert_called_once()
        mock_metric_sender.send_message_sent_metric.assert_not_called()

        # Correlation: verify the NACK is traceable back to the original message
        # (message_id from MSH-10, correlation_id from Service Bus metadata, ack_code, endpoint).
        expected_attributes = {
            "ack_code": "AE",
            "correlation_id": "N/A",
            "message_id": "MSGID1234",
            "endpoint": "mpi.example.org:2575",
        }
        mock_metric_sender.send_message_nack_ae_metric.assert_called_once_with(attributes=expected_attributes)
        mock_metric_sender.send_message_retry_attempt_metric.assert_called_once_with(attributes=expected_attributes)
        mock_throttler.wait_if_needed.assert_called_once()

        # Surfacing for operations: logs must include the ACK code and downstream endpoint.
        failed_log_message = mock_event_logger.log_message_failed.call_args.args[1]
        self.assertIn("AE", failed_log_message)
        self.assertIn("mpi.example.org:2575", failed_log_message)

        self.assertFalse(result)

    @patch("hl7_subscription_sender.application.parse_message")
    @patch("hl7_subscription_sender.application.get_ack_result")
    def test_process_message_ar_ack_dead_letters_message(
        self, mock_ack_processor: Mock, mock_parse_message: Mock
    ) -> None:
        (
            service_bus_message,
            hl7_message,
            hl7_string,
            mock_hl7_subscription_sender_client,
            mock_event_logger,
            mock_metric_sender,
            mock_throttler,
        ) = _setup()
        mock_parse_message.return_value = hl7_message
        hl7_ack_message = "HL7 ack message"
        mock_hl7_subscription_sender_client.send_message.return_value = hl7_ack_message
        mock_hl7_subscription_sender_client.receiver_mllp_hostname = "mpi.example.org"
        mock_hl7_subscription_sender_client.receiver_mllp_port = 2575
        mock_ack_processor.return_value = AckResult(AckOutcome.AR, "AR", "MSGID1234", hl7_ack_message)

        with self.assertRaises(DeadLetterMessage) as ctx:
            _process_message(
                service_bus_message,
                mock_hl7_subscription_sender_client,
                mock_event_logger,
                mock_metric_sender,
                mock_throttler,
            )

        self.assertEqual(ctx.exception.reason, "AR")
        # Correlation: the dead-letter description and the AR metric both carry the
        # original message's correlation_id/message_id so operators can trace the NACK back to it.
        self.assertIn("message_id=MSGID1234", ctx.exception.description)
        self.assertIn("correlation_id=N/A", ctx.exception.description)
        mock_event_logger.log_message_failed.assert_called_once()
        mock_metric_sender.send_message_sent_metric.assert_not_called()
        expected_attributes = {
            "ack_code": "AR",
            "correlation_id": "N/A",
            "message_id": "MSGID1234",
            "endpoint": "mpi.example.org:2575",
        }
        mock_metric_sender.send_message_nack_ar_metric.assert_called_once_with(attributes=expected_attributes)
        mock_metric_sender.send_message_nack_ae_metric.assert_not_called()

        # Surfacing for operations: logs must include the ACK code and downstream endpoint.
        failed_log_message = mock_event_logger.log_message_failed.call_args.args[1]
        self.assertIn("AR", failed_log_message)
        self.assertIn("mpi.example.org:2575", failed_log_message)

    @patch("hl7_subscription_sender.application.parse_message")
    @patch("hl7_subscription_sender.application.get_ack_result")
    def test_process_message_ar_still_dead_letters_when_metric_send_fails(
        self, mock_ack_processor: Mock, mock_parse_message: Mock
    ) -> None:
        """A telemetry failure must not change the non-recoverable (AR) delivery decision."""
        (
            service_bus_message,
            hl7_message,
            hl7_string,
            mock_hl7_subscription_sender_client,
            mock_event_logger,
            mock_metric_sender,
            mock_throttler,
        ) = _setup()
        mock_parse_message.return_value = hl7_message
        hl7_ack_message = "HL7 ack message"
        mock_hl7_subscription_sender_client.send_message.return_value = hl7_ack_message
        mock_ack_processor.return_value = AckResult(AckOutcome.AR, "AR", "MSGID1234", hl7_ack_message)
        mock_metric_sender.send_message_nack_ar_metric.side_effect = RuntimeError("Azure Monitor unavailable")

        with self.assertRaises(DeadLetterMessage) as ctx:
            _process_message(
                service_bus_message,
                mock_hl7_subscription_sender_client,
                mock_event_logger,
                mock_metric_sender,
                mock_throttler,
            )

        self.assertEqual(ctx.exception.reason, "AR")

    @patch("hl7_subscription_sender.application.parse_message")
    def test_process_message_send_errors(self, mock_parse_message: Mock) -> None:
        error_cases = [
            {"description": "timeout_error", "error": TimeoutError("No ACK received within 30 seconds")},
            {"description": "connection_error", "error": ConnectionError("Connection failed")},
        ]

        for case in error_cases:
            with self.subTest(error=case["description"]):
                (
                    service_bus_message,
                    hl7_message,
                    hl7_string,
                    mock_hl7_subscription_sender_client,
                    mock_event_logger,
                    mock_metric_sender,
                    mock_throttler,
                ) = _setup()
                mock_parse_message.return_value = hl7_message
                mock_hl7_subscription_sender_client.send_message.side_effect = case["error"]

                result = _process_message(
                    service_bus_message,
                    mock_hl7_subscription_sender_client,
                    mock_event_logger,
                    mock_metric_sender,
                    mock_throttler,
                )

                self._assert_error_handling(result, mock_event_logger, mock_metric_sender)
                mock_throttler.wait_if_needed.assert_called_once()

    @patch("hl7_subscription_sender.application.parse_message")
    def test_process_message_unexpected_error(self, mock_parse_message: Mock) -> None:
        (
            service_bus_message,
            hl7_message,
            hl7_string,
            mock_hl7_subscription_sender_client,
            mock_event_logger,
            mock_metric_sender,
            mock_throttler,
        ) = _setup()
        mock_parse_message.side_effect = Exception("Unexpected error")

        result = _process_message(
            service_bus_message,
            mock_hl7_subscription_sender_client,
            mock_event_logger,
            mock_metric_sender,
            mock_throttler,
        )

        self._assert_error_handling(result, mock_event_logger, mock_metric_sender)
        mock_throttler.wait_if_needed.assert_not_called()

    @patch("hl7_subscription_sender.application.ConnectionConfig")
    @patch("hl7_subscription_sender.application.ServiceBusClientFactory")
    @patch("hl7_subscription_sender.application.AppConfig")
    @patch("hl7_subscription_sender.application.TCPHealthCheckServer")
    @patch("hl7_subscription_sender.application.HL7SubscriptionSenderClient")
    @patch("hl7_subscription_sender.application.EventLogger")
    def test_health_check_server_starts_and_stops(
        self,
        mock_event_logger: Mock,
        mock_hl7_subscription_sender_client: Mock,
        mock_health_check: Mock,
        mock_app_config: Mock,
        mock_factory: Mock,
        mock_connection_config: Mock,
    ) -> None:
        mock_health_server = MagicMock()
        mock_health_check_ctx = MagicMock()
        mock_health_check_ctx.__enter__.return_value = mock_health_server
        mock_health_check.return_value = mock_health_check_ctx
        mock_app_config.read_env_config.return_value = AppConfig(
            connection_string=None,
            ingress_session_id="test-session-id",
            service_bus_namespace=None,
            receiver_mllp_hostname="test-hostname",
            receiver_mllp_port=2575,
            health_check_hostname="localhost",
            health_check_port=9000,
            workflow_id="test_workflow_id",
            microservice_id="test_microservice_id",
            health_board="test-health-board",
            peer_service="test-service",
            ack_timeout_seconds=30,
            max_messages_per_minute=None,
            ingress_topic_name="test-topic",
            ingress_subscription_name="test-subscription",
        )
        with patch("hl7_subscription_sender.application.ProcessorManager") as mock_processor_manager:
            mock_instance = mock_processor_manager.return_value
            mock_instance.is_running = False

            main()

            mock_health_check.assert_called_once_with("localhost", 9000)
            mock_health_server.start.assert_called_once()
            mock_health_check_ctx.__exit__.assert_called_once()


class TestBatchSizing(unittest.TestCase):
    def test_uses_max_batch_when_no_throttle(self) -> None:
        throttler = MagicMock(interval_seconds=None)

        batch_size = _calculate_batch_size(throttler)

        self.assertEqual(batch_size, MAX_BATCH_SIZE)

    def test_reduces_batch_when_interval_exceeds_lock_window(self) -> None:
        throttler = MagicMock(interval_seconds=60.0)  # one message per minute

        with patch("hl7_subscription_sender.application.SubscriptionReceiverClient.LOCK_RENEWAL_DURATION_SECONDS", 900):
            batch_size = _calculate_batch_size(throttler)

        self.assertEqual(batch_size, 15)  # (900-30)/60 = 14 intervals => 15 messages


if __name__ == "__main__":
    unittest.main()
