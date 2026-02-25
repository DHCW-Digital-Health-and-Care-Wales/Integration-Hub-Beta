import unittest
from datetime import datetime, timezone

from message_store_service.message_record import MessageRecord


class TestMessageRecord(unittest.TestCase):
    """Tests for the MessageRecord dataclass."""

    def test_construction_with_all_fields(self) -> None:
        """Verify a MessageRecord can be created with all fields populated."""
        received_at = datetime(2025, 6, 1, 10, 0, 0, tzinfo=timezone.utc)

        record = MessageRecord(
            received_at=received_at,
            correlation_id="abc-123",
            source_system="PARIS",
            processing_component="message_store_service",
            target_system="MPI",
            raw_payload="MSH|^~\\&|SENDING|FAC||",
            xml_payload="<message/>",
        )

        self.assertEqual(record.received_at, received_at)
        self.assertEqual(record.correlation_id, "abc-123")
        self.assertEqual(record.source_system, "PARIS")
        self.assertEqual(record.processing_component, "message_store_service")
        self.assertEqual(record.target_system, "MPI")
        self.assertEqual(record.raw_payload, "MSH|^~\\&|SENDING|FAC||")
        self.assertEqual(record.xml_payload, "<message/>")

    def test_construction_with_optional_fields_none(self) -> None:
        """Verify optional fields (target_system, xml_payload) accept None."""
        record = MessageRecord(
            received_at=datetime(2025, 6, 1, 10, 0, 0, tzinfo=timezone.utc),
            correlation_id="abc-123",
            source_system="PHW",
            processing_component="message_store_service",
            target_system=None,
            raw_payload="MSH|^~\\&|SENDING|FAC||",
            xml_payload=None,
        )

        self.assertIsNone(record.target_system)
        self.assertIsNone(record.xml_payload)


if __name__ == "__main__":
    unittest.main()
