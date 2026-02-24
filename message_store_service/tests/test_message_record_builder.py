import json
import unittest
from unittest.mock import MagicMock, patch

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

    @patch("message_store_service.message_record_builder.datetime")
    def test_build_message_record_parses_json_with_all_fields(self, mock_dt: MagicMock) -> None:
        """Verify all fields are extracted from JSON body."""
        mock_dt.now.return_value.isoformat.return_value = "2025-06-01T10:00:01+00:00"

        data = {
            "received_at": "2025-06-01T09:59:00+00:00",
            "correlation_id": "corr-123",
            "source_system": "PARIS",
            "processing_component": "message_store_service",
            "target_system": "MPI",
            "raw_payload": "MSH|^~\\&|PARIS|FAC|MPI|RECEIVING|...",
            "xml_payload": "<message/>",
        }
        msg = self._make_message_with_json_body(data)

        record = build_message_record(msg)

        self.assertIsInstance(record, MessageRecord)
        self.assertEqual(record.received_at, "2025-06-01T09:59:00+00:00")
        self.assertEqual(record.stored_at, "2025-06-01T10:00:01+00:00")
        self.assertEqual(record.correlation_id, "corr-123")
        self.assertEqual(record.source_system, "PARIS")
        self.assertEqual(record.processing_component, "message_store_service")
        self.assertEqual(record.target_system, "MPI")
        self.assertEqual(record.raw_payload, "MSH|^~\\&|PARIS|FAC|MPI|RECEIVING|...")
        self.assertEqual(record.xml_payload, "<message/>")

    @patch("message_store_service.message_record_builder.datetime")
    def test_build_message_record_with_optional_fields_missing(self, mock_dt: MagicMock) -> None:
        """When optional fields (target_system, xml_payload) are missing, they default to None."""
        mock_dt.now.return_value.isoformat.return_value = "2025-06-01T10:00:01+00:00"

        data = {
            "received_at": "2025-06-01T09:59:00+00:00",
            "correlation_id": "corr-456",
            "source_system": "PHW",
            "processing_component": "hl7_phw_transformer",
            "raw_payload": "MSH|^~\\&|PHW|...",
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
            "received_at": "2025-06-01T09:59:00+00:00",
            "correlation_id": "corr-789",
            # Missing source_system, processing_component and raw_payload
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

    @patch("message_store_service.message_record_builder.datetime")
    def test_build_message_record_with_empty_optional_fields(self, mock_dt: MagicMock) -> None:
        """When optional fields are present but empty strings, they are preserved."""
        mock_dt.now.return_value.isoformat.return_value = "2025-06-01T10:00:01+00:00"

        data = {
            "received_at": "2025-06-01T09:59:00+00:00",
            "correlation_id": "corr-111",
            "source_system": "SYS",
            "processing_component": "test_service",
            "target_system": "",
            "raw_payload": "MSH|...",
            "xml_payload": "",
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

    @patch("message_store_service.message_record_builder.datetime")
    def test_build_message_records_returns_list_of_records(self, mock_dt: MagicMock) -> None:
        mock_dt.now.return_value.isoformat.return_value = "2025-06-01T10:00:01+00:00"

        messages = [
            self._make_message({
                "received_at": "2025-06-01T09:59:00+00:00",
                "correlation_id": "c1",
                "source_system": "S1",
                "processing_component": "svc1",
                "raw_payload": "body1",
            }),
            self._make_message({
                "received_at": "2025-06-01T09:59:01+00:00",
                "correlation_id": "c2",
                "source_system": "S2",
                "processing_component": "svc2",
                "raw_payload": "body2",
            }),
        ]

        records = build_message_records(messages)

        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].correlation_id, "c1")
        self.assertEqual(records[1].correlation_id, "c2")

    @patch("message_store_service.message_record_builder.datetime")
    def test_build_message_records_empty_list(self, mock_dt: MagicMock) -> None:
        """An empty message list should return an empty record list."""
        records = build_message_records([])
        self.assertEqual(records, [])


if __name__ == "__main__":
    unittest.main()



