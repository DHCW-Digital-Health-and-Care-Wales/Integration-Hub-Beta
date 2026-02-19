import json
import unittest
from unittest.mock import MagicMock, patch

from message_bus_lib.message_store_client import MessageStoreClient


class TestMessageStoreClient(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_sender = MagicMock()
        self.client = MessageStoreClient(self.mock_sender, "test-microservice", "test-peer")

    def test_send_to_store_sends_correct_json(self) -> None:
        self.client.send_to_store(
            message_received_at="2025-01-01T00:00:00+00:00",
            correlation_id="test-uuid",
            source_system="252",
            raw_payload="MSH|^~\\&|...",
        )

        self.mock_sender.send_text_message.assert_called_once()
        sent_json = self.mock_sender.send_text_message.call_args[0][0]
        sent_data = json.loads(sent_json)

        self.assertEqual(sent_data["MessageReceivedAt"], "2025-01-01T00:00:00+00:00")
        self.assertEqual(sent_data["CorrelationId"], "test-uuid")
        self.assertEqual(sent_data["SourceSystem"], "252")
        self.assertEqual(sent_data["ProcessingComponent"], "test-microservice")
        self.assertEqual(sent_data["TargetSystem"], "test-peer")
        self.assertEqual(sent_data["RawPayload"], "MSH|^~\\&|...")
        self.assertIsNone(sent_data["XmlPayload"])

    def test_send_to_store_with_xml_payload(self) -> None:
        self.client.send_to_store(
            message_received_at="2025-01-01T00:00:00+00:00",
            correlation_id="test-uuid",
            source_system="252",
            raw_payload="MSH|^~\\&|...",
            xml_payload="<xml>message</xml>",
        )

        sent_json = self.mock_sender.send_text_message.call_args[0][0]
        sent_data = json.loads(sent_json)

        self.assertEqual(sent_data["XmlPayload"], "<xml>message</xml>")

    def test_send_to_store_with_explicit_target_system(self) -> None:
        self.client.send_to_store(
            message_received_at="2025-01-01T00:00:00+00:00",
            correlation_id="test-uuid",
            source_system="252",
            raw_payload="MSH|^~\\&|...",
            target_system="custom-target",
        )

        sent_json = self.mock_sender.send_text_message.call_args[0][0]
        sent_data = json.loads(sent_json)

        self.assertEqual(sent_data["TargetSystem"], "custom-target")

    def test_send_to_store_defaults_target_system_to_peer_service(self) -> None:
        self.client.send_to_store(
            message_received_at="2025-01-01T00:00:00+00:00",
            correlation_id="test-uuid",
            source_system="252",
            raw_payload="MSH|^~\\&|...",
        )

        sent_json = self.mock_sender.send_text_message.call_args[0][0]
        sent_data = json.loads(sent_json)

        self.assertEqual(sent_data["TargetSystem"], "test-peer")

    def test_send_to_store_raises_on_send_failure(self) -> None:
        self.mock_sender.send_text_message.side_effect = Exception("Service Bus error")

        with self.assertRaises(Exception) as context:
            self.client.send_to_store(
                message_received_at="2025-01-01T00:00:00+00:00",
                correlation_id="test-uuid",
                source_system="252",
                raw_payload="MSH|^~\\&|...",
            )

        self.assertIn("Service Bus error", str(context.exception))

    @patch("message_bus_lib.message_store_client.logger")
    def test_send_to_store_logs_on_success(self, mock_logger: MagicMock) -> None:
        self.client.send_to_store(
            message_received_at="2025-01-01T00:00:00+00:00",
            correlation_id="test-uuid",
            source_system="252",
            raw_payload="MSH|^~\\&|...",
        )

        mock_logger.info.assert_called_once_with("Message store event sent - CorrelationId: %s", "test-uuid")

    @patch("message_bus_lib.message_store_client.logger")
    def test_send_to_store_logs_on_failure(self, mock_logger: MagicMock) -> None:
        self.mock_sender.send_text_message.side_effect = Exception("Send failed")

        with self.assertRaises(Exception):
            self.client.send_to_store(
                message_received_at="2025-01-01T00:00:00+00:00",
                correlation_id="test-uuid",
                source_system="252",
                raw_payload="MSH|^~\\&|...",
            )

        mock_logger.error.assert_called_once()

    def test_close_closes_sender(self) -> None:
        self.client.close()

        self.mock_sender.close.assert_called_once()

    def test_context_manager_closes_on_exit(self) -> None:
        with MessageStoreClient(self.mock_sender, "test-microservice", "test-peer"):
            pass

        self.mock_sender.close.assert_called_once()

    def test_send_to_store_all_fields_present_in_json(self) -> None:
        self.client.send_to_store(
            message_received_at="2025-02-19T10:00:00+00:00",
            correlation_id="abc-123",
            source_system="SRC",
            raw_payload="RAW_DATA",
            xml_payload="<xml/>",
            target_system="TGT",
        )

        sent_json = self.mock_sender.send_text_message.call_args[0][0]
        sent_data = json.loads(sent_json)

        expected_keys = {
            "MessageReceivedAt",
            "CorrelationId",
            "SourceSystem",
            "ProcessingComponent",
            "TargetSystem",
            "RawPayload",
            "XmlPayload",
        }
        self.assertEqual(set(sent_data.keys()), expected_keys)


if __name__ == "__main__":
    unittest.main()
