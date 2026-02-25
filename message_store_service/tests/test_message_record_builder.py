import json
import unittest
from datetime import datetime
from unittest.mock import MagicMock

from azure.servicebus import ServiceBusMessage

from message_store_service.message_record import MessageRecord
from message_store_service.message_record_builder import build_message_record, build_message_records


class TestBuildMessageRecord(unittest.TestCase):
    """Tests for build_message_record — parsing JSON message body."""

    def _make_message_with_json_body(self, data: dict) -> MagicMock:  # type: ignore[type-arg]
        """Create a mock ServiceBusMessage with JSON body."""
        msg = MagicMock(spec=ServiceBusMessage)
        msg.body = [json.dumps(data).encode("utf-8")]
        return msg

    def test_build_message_record_parses_json_with_all_fields(self) -> None:
        received_at = "2025-06-01T09:59:00+00:00"

        data = {
            "MessageReceivedAt": received_at,
            "CorrelationId": "corr-123",
            "SourceSystem": "PARIS",
            "ProcessingComponent": "message_store_service",
            "TargetSystem": "MPI",
            "RawPayload": "MSH|^~\\&|PARIS|FAC|MPI|RECEIVING|...",
            "XmlPayload": "<message/>",
        }
        msg = self._make_message_with_json_body(data)

        record = build_message_record(msg)

        self.assertIsInstance(record, MessageRecord)
        self.assertEqual(record.received_at, datetime.fromisoformat(received_at))
        self.assertEqual(record.correlation_id, "corr-123")
        self.assertEqual(record.source_system, "PARIS")
        self.assertEqual(record.processing_component, "message_store_service")
        self.assertEqual(record.target_system, "MPI")
        self.assertEqual(record.raw_payload, "MSH|^~\\&|PARIS|FAC|MPI|RECEIVING|...")
        self.assertEqual(record.xml_payload, "<message/>")

    def test_build_message_record_with_optional_fields_missing(self) -> None:
        """When optional fields (TargetSystem, XmlPayload) are missing, they default to None."""
        data = {
            "MessageReceivedAt": "2025-06-01T09:59:00+00:00",
            "CorrelationId": "corr-456",
            "SourceSystem": "PHW",
            "ProcessingComponent": "hl7_phw_transformer",
            "RawPayload": "MSH|^~\\&|PHW|...",
        }
        msg = self._make_message_with_json_body(data)

        record = build_message_record(msg)

        self.assertEqual(record.correlation_id, "corr-456")
        self.assertEqual(record.source_system, "PHW")
        self.assertEqual(record.processing_component, "hl7_phw_transformer")
        self.assertIsNone(record.target_system)
        self.assertIsNone(record.xml_payload)

    def test_build_message_record_raises_on_invalid_json(self) -> None:
        """If the message body is not valid JSON, ValueError should be raised."""
        msg = MagicMock(spec=ServiceBusMessage)
        msg.body = [b"{invalid json}"]

        with self.assertRaises(ValueError) as ctx:
            build_message_record(msg)

        self.assertIn("Invalid JSON", str(ctx.exception))

    def test_build_message_record_raises_on_missing_required_field(self) -> None:
        """If a required field is missing, KeyError should be raised."""
        data = {
            "MessageReceivedAt": "2025-06-01T09:59:00+00:00",
            "CorrelationId": "corr-789",
            # Missing SourceSystem, ProcessingComponent and RawPayload
        }
        msg = self._make_message_with_json_body(data)

        with self.assertRaises(KeyError) as ctx:
            build_message_record(msg)

        self.assertIn("Missing required field", str(ctx.exception))

    def test_build_message_record_raises_on_decode_error(self) -> None:
        """If the message body contains invalid UTF-8, a decode error should propagate."""
        msg = MagicMock(spec=ServiceBusMessage)
        msg.body = [b"\xff\xfe"]  # Invalid UTF-8 sequence

        with self.assertRaises(UnicodeDecodeError):
            build_message_record(msg)

    def test_build_message_record_raises_on_invalid_received_at_format(self) -> None:
        data = {
            "MessageReceivedAt": "not-a-datetime",
            "CorrelationId": "corr-000",
            "SourceSystem": "SRC",
            "ProcessingComponent": "svc",
            "RawPayload": "MSH|...",
        }
        msg = self._make_message_with_json_body(data)

        with self.assertRaises(ValueError) as ctx:
            build_message_record(msg)

        self.assertIn("Invalid received_at timestamp", str(ctx.exception))

    def test_build_message_record_with_empty_optional_fields(self) -> None:
        """When optional fields are present but empty strings, they are preserved."""
        data = {
            "MessageReceivedAt": "2025-06-01T09:59:00+00:00",
            "CorrelationId": "corr-111",
            "SourceSystem": "SYS",
            "ProcessingComponent": "test_service",
            "TargetSystem": "",
            "RawPayload": "MSH|...",
            "XmlPayload": "",
        }
        msg = self._make_message_with_json_body(data)

        record = build_message_record(msg)

        self.assertEqual(record.target_system, "")
        self.assertEqual(record.xml_payload, "")


class TestBuildMessageRecords(unittest.TestCase):
    """Tests for build_message_records — batch conversion."""

    def _make_message(self, data: dict) -> MagicMock:  # type: ignore[type-arg]
        msg = MagicMock(spec=ServiceBusMessage)
        msg.body = [json.dumps(data).encode("utf-8")]
        return msg

    def test_build_message_records_returns_list_of_records(self) -> None:
        messages = [
            self._make_message({
                "MessageReceivedAt": "2025-06-01T09:59:00+00:00",
                "CorrelationId": "c1",
                "SourceSystem": "S1",
                "ProcessingComponent": "svc1",
                "RawPayload": "body1",
            }),
            self._make_message({
                "MessageReceivedAt": "2025-06-01T09:59:01+00:00",
                "CorrelationId": "c2",
                "SourceSystem": "S2",
                "ProcessingComponent": "svc2",
                "RawPayload": "body2",
            }),
        ]

        records = build_message_records(messages)

        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].correlation_id, "c1")
        self.assertEqual(records[1].correlation_id, "c2")

    def test_build_message_records_empty_list(self) -> None:
        """An empty message list should return an empty record list."""
        records = build_message_records([])
        self.assertEqual(records, [])


if __name__ == "__main__":
    unittest.main()

