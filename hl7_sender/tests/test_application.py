import unittest
from unittest.mock import MagicMock, Mock, patch

from azure.servicebus import ServiceBusMessage
from hl7apy.core import Message

from hl7_sender.app_config import AppConfig
from hl7_sender.application import (
    MAX_BATCH_SIZE,
    _calculate_batch_size,
    _process_message,
    main,
)


def _setup() -> tuple[ServiceBusMessage, Message, str, MagicMock, MagicMock, MagicMock, MagicMock, MagicMock]:
    hl7_message = Message("ADT_A01")
    hl7_message.msh.msh_10 = "MSGID1234"
    hl7_string = hl7_message.to_er7()
    service_bus_message = ServiceBusMessage(body=hl7_string)
    mock_hl7_sender_client = MagicMock()
    mock_event_logger = MagicMock()
    mock_metric_sender = MagicMock()
    mock_throttler = MagicMock()
    mock_message_store = MagicMock()

    return (
        service_bus_message,
        hl7_message,
        hl7_string,
        mock_hl7_sender_client,
        mock_event_logger,
        mock_metric_sender,
        mock_throttler,
        mock_message_store,
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
        (
            service_bus_message,
            hl7_message,
            hl7_string,
            mock_hl7_sender_client,
            mock_event_logger,
            mock_metric_sender,
            mock_throttler,
            mock_message_store,
        ) = _setup()
        mock_parse_message.return_value = hl7_message
        hl7_ack_message = "HL7 ack message"
        mock_hl7_sender_client.send_message.return_value = hl7_ack_message
        mock_ack_processor.return_value = True

        result = _process_message(
            service_bus_message,
            mock_hl7_sender_client,
            mock_event_logger,
            mock_metric_sender,
            mock_throttler,
            mock_message_store,
        )

        mock_parse_message.assert_called_once_with(hl7_string)
        mock_ack_processor.assert_called_once_with(hl7_ack_message)
        mock_event_logger.log_message_received.assert_called_once()
        mock_event_logger.log_message_processed.assert_called_once()
        mock_metric_sender.send_message_sent_metric.assert_called_once()
        mock_throttler.wait_if_needed.assert_called_once()

        self.assertTrue(result)

    @patch("hl7_sender.application.parse_message")
    @patch("hl7_sender.application.get_ack_result")
    def test_process_message_success_with_negative_ack(
        self, mock_ack_processor: Mock, mock_parse_message: Mock
    ) -> None:
        (
            service_bus_message,
            hl7_message,
            hl7_string,
            mock_hl7_sender_client,
            mock_event_logger,
            mock_metric_sender,
            mock_throttler,
            mock_message_store,
        ) = _setup()
        mock_parse_message.return_value = hl7_message
        hl7_ack_message = "HL7 ack message"
        mock_hl7_sender_client.send_message.return_value = hl7_ack_message
        mock_ack_processor.return_value = False

        result = _process_message(
            service_bus_message,
            mock_hl7_sender_client,
            mock_event_logger,
            mock_metric_sender,
            mock_throttler,
            mock_message_store,
        )

        mock_parse_message.assert_called_once_with(hl7_string)
        mock_ack_processor.assert_called_once_with(hl7_ack_message)
        mock_event_logger.log_message_received.assert_called_once()
        mock_event_logger.log_message_processed.assert_called_once()
        mock_metric_sender.send_message_sent_metric.assert_not_called()
        mock_throttler.wait_if_needed.assert_called_once()

        self.assertFalse(result)

    @patch("hl7_sender.application.parse_message")
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
                    mock_hl7_sender_client,
                    mock_event_logger,
                    mock_metric_sender,
                    mock_throttler,
                    mock_message_store,
                ) = _setup()
                mock_parse_message.return_value = hl7_message
                mock_hl7_sender_client.send_message.side_effect = case["error"]

                result = _process_message(
                    service_bus_message,
                    mock_hl7_sender_client,
                    mock_event_logger,
                    mock_metric_sender,
                    mock_throttler,
                    mock_message_store,
                )

                self._assert_error_handling(result, mock_event_logger, mock_metric_sender)
                mock_throttler.wait_if_needed.assert_called_once()

    @patch("hl7_sender.application.parse_message")
    def test_process_message_unexpected_error(self, mock_parse_message: Mock) -> None:
        (
            service_bus_message,
            hl7_message,
            hl7_string,
            mock_hl7_sender_client,
            mock_event_logger,
            mock_metric_sender,
            mock_throttler,
            mock_message_store,
        ) = _setup()
        mock_parse_message.side_effect = Exception("Unexpected error")

        result = _process_message(
            service_bus_message,
            mock_hl7_sender_client,
            mock_event_logger,
            mock_metric_sender,
            mock_throttler,
            mock_message_store,
        )

        self._assert_error_handling(result, mock_event_logger, mock_metric_sender)
        mock_throttler.wait_if_needed.assert_not_called()

    @patch("hl7_sender.application.ConnectionConfig")
    @patch("hl7_sender.application.ServiceBusClientFactory")
    @patch("hl7_sender.application.AppConfig")
    @patch("hl7_sender.application.TCPHealthCheckServer")
    @patch("hl7_sender.application.HL7SenderClient")
    @patch("hl7_sender.application.EventLogger")
    @patch("hl7_sender.application.MessageStoreClient")
    def test_health_check_server_starts_and_stops(
        self,
        mock_message_store_cls: Mock,
        mock_event_logger: Mock,
        mock_hl7_sender: Mock,
        mock_health_check: Mock,
        mock_app_config: Mock,
        mock_factory: Mock,
        mock_connection_config: Mock,
    ) -> None:
        mock_health_server = MagicMock()
        mock_health_check_ctx = MagicMock()
        mock_health_check_ctx.__enter__.return_value = mock_health_server
        mock_health_check.return_value = mock_health_check_ctx
        mock_message_store_instance = MagicMock()
        mock_message_store_instance.__enter__ = MagicMock(return_value=mock_message_store_instance)
        mock_message_store_instance.__exit__ = MagicMock(return_value=False)
        mock_message_store_cls.return_value = mock_message_store_instance
        mock_app_config.read_env_config.return_value = AppConfig(
            connection_string=None,
            ingress_queue_name="test-queue-name",
            ingress_session_id="test-session-id",
            service_bus_namespace=None,
            receiver_mllp_hostname="test-hostname",
            receiver_mllp_port=2575,
            health_check_hostname="localhost",
            health_check_port=9000,
            message_store_queue_name="test-messagestore-queue",
            workflow_id="test_workflow_id",
            microservice_id="test_microservice_id",
            health_board="test-health-board",
            peer_service="test-service",
            ack_timeout_seconds=30,
            max_messages_per_minute=None,
        )
        with patch("hl7_sender.application.ProcessorManager") as mock_processor_manager:
            mock_instance = mock_processor_manager.return_value
            mock_instance.is_running = False

            main()

            mock_health_check.assert_called_once_with("localhost", 9000)
            mock_health_server.start.assert_called_once()
            mock_health_check_ctx.__exit__.assert_called_once()

    @patch("hl7_sender.application.parse_message")
    @patch("hl7_sender.application.get_ack_result")
    @patch("hl7_sender.application.convert_er7_to_xml")
    def test_process_message_sends_to_message_store(
        self, mock_convert_xml: Mock, mock_ack_processor: Mock, mock_parse_message: Mock
    ) -> None:
        (
            service_bus_message,
            hl7_message,
            hl7_string,
            mock_hl7_sender_client,
            mock_event_logger,
            mock_metric_sender,
            mock_throttler,
            mock_message_store,
        ) = _setup()
        mock_parse_message.return_value = hl7_message
        mock_hl7_sender_client.send_message.return_value = "ACK"
        mock_ack_processor.return_value = True
        mock_convert_xml.return_value = "<xml>content</xml>"

        _process_message(
            service_bus_message,
            mock_hl7_sender_client,
            mock_event_logger,
            mock_metric_sender,
            mock_throttler,
            mock_message_store,
        )

        mock_message_store.send_to_store.assert_called_once()
        call_kwargs = mock_message_store.send_to_store.call_args.kwargs
        self.assertEqual(call_kwargs["raw_payload"], hl7_string)
        self.assertEqual(call_kwargs["xml_payload"], "<xml>content</xml>")
        self.assertIn("message_received_at", call_kwargs)
        self.assertIn("correlation_id", call_kwargs)

    @patch("hl7_sender.application.parse_message")
    @patch("hl7_sender.application.get_ack_result")
    @patch("hl7_sender.application.convert_er7_to_xml")
    def test_message_store_xml_generation_failure_still_sends(
        self, mock_convert_xml: Mock, mock_ack_processor: Mock, mock_parse_message: Mock
    ) -> None:
        (
            service_bus_message,
            hl7_message,
            hl7_string,
            mock_hl7_sender_client,
            mock_event_logger,
            mock_metric_sender,
            mock_throttler,
            mock_message_store,
        ) = _setup()
        mock_parse_message.return_value = hl7_message
        mock_hl7_sender_client.send_message.return_value = "ACK"
        mock_ack_processor.return_value = True
        mock_convert_xml.side_effect = ValueError("Cannot parse")

        _process_message(
            service_bus_message,
            mock_hl7_sender_client,
            mock_event_logger,
            mock_metric_sender,
            mock_throttler,
            mock_message_store,
        )

        mock_message_store.send_to_store.assert_called_once()
        call_kwargs = mock_message_store.send_to_store.call_args.kwargs
        self.assertIsNone(call_kwargs["xml_payload"])
        self.assertEqual(call_kwargs["raw_payload"], hl7_string)

    @patch("hl7_sender.application.parse_message")
    @patch("hl7_sender.application.get_ack_result")
    @patch("hl7_sender.application.convert_er7_to_xml")
    def test_message_store_failure_does_not_block_result(
        self, mock_convert_xml: Mock, mock_ack_processor: Mock, mock_parse_message: Mock
    ) -> None:
        (
            service_bus_message,
            hl7_message,
            hl7_string,
            mock_hl7_sender_client,
            mock_event_logger,
            mock_metric_sender,
            mock_throttler,
            mock_message_store,
        ) = _setup()
        mock_parse_message.return_value = hl7_message
        mock_hl7_sender_client.send_message.return_value = "ACK"
        mock_ack_processor.return_value = True
        mock_convert_xml.return_value = "<xml/>"
        mock_message_store.send_to_store.side_effect = Exception("Store unavailable")

        result = _process_message(
            service_bus_message,
            mock_hl7_sender_client,
            mock_event_logger,
            mock_metric_sender,
            mock_throttler,
            mock_message_store,
        )

        self.assertTrue(result)
        mock_event_logger.log_message_processed.assert_called_once()

    @patch("hl7_sender.application.parse_message")
    @patch("hl7_sender.application.get_ack_result")
    @patch("hl7_sender.application.convert_er7_to_xml")
    def test_message_store_forwards_upstream_metadata(
        self, mock_convert_xml: Mock, mock_ack_processor: Mock, mock_parse_message: Mock
    ) -> None:
        (
            service_bus_message,
            hl7_message,
            hl7_string,
            mock_hl7_sender_client,
            mock_event_logger,
            mock_metric_sender,
            mock_throttler,
            mock_message_store,
        ) = _setup()

        # Add metadata to service bus message
        original_timestamp = "2025-05-05T10:30:00+00:00"
        original_correlation_id = "upstream-correlation-id-123"
        service_bus_message.application_properties = {
            "MessageReceivedAt": original_timestamp,
            "CorrelationId": original_correlation_id,
            "SourceSystem": "PHW",
        }

        mock_parse_message.return_value = hl7_message
        mock_hl7_sender_client.send_message.return_value = "ACK"
        mock_ack_processor.return_value = True
        mock_convert_xml.return_value = "<xml/>"

        _process_message(
            service_bus_message,
            mock_hl7_sender_client,
            mock_event_logger,
            mock_metric_sender,
            mock_throttler,
            mock_message_store,
        )

        mock_message_store.send_to_store.assert_called_once()
        call_kwargs = mock_message_store.send_to_store.call_args.kwargs

        # Verify upstream metadata is forwarded, not regenerated
        self.assertEqual(call_kwargs["message_received_at"], original_timestamp)
        self.assertEqual(call_kwargs["correlation_id"], original_correlation_id)
        self.assertEqual(call_kwargs["source_system"], "PHW")


class TestBatchSizing(unittest.TestCase):
    def test_uses_max_batch_when_no_throttle(self) -> None:
        throttler = MagicMock(interval_seconds=None)

        batch_size = _calculate_batch_size(throttler)

        self.assertEqual(batch_size, MAX_BATCH_SIZE)

    def test_reduces_batch_when_interval_exceeds_lock_window(self) -> None:
        throttler = MagicMock(interval_seconds=60.0)  # one message per minute

        with patch("hl7_sender.application.MessageReceiverClient.LOCK_RENEWAL_DURATION_SECONDS", 900):
            batch_size = _calculate_batch_size(throttler)

        self.assertEqual(batch_size, 15)  # (900-30)/60 = 14 intervals => 15 messages


if __name__ == "__main__":
    unittest.main()
