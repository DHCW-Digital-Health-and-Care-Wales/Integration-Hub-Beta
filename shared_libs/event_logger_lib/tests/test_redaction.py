import unittest

from event_logger_lib.redaction import REDACTION_MASK, redact_hl7_message


class TestRedactHl7Message(unittest.TestCase):
    def _adt_message(self) -> str:
        return (
            "MSH|^~\\&|SENDING_APP|SENDING_FAC|RECV_APP|RECV_FAC|20250101120000||ADT^A28|MSG00001|P|2.5\r"
            "PID|1||123456^^^NHS^MR||SMITH^JOHN^A||19870101|M|||1 HIGH ST^^CARDIFF^^CF10 1AA\r"
            "NK1|1|SMITH^JANE|SPO\r"
            "PV1|1|I|WARD^BED^ROOM"
        )

    def test_msh_routing_fields_retained(self):
        redacted = redact_hl7_message(self._adt_message())

        # Encoding chars and routing/metadata fields are preserved.
        self.assertIn("MSH|^~\\&|SENDING_APP|SENDING_FAC|RECV_APP|RECV_FAC", redacted)
        self.assertIn("20250101120000", redacted)
        self.assertIn("ADT^A28", redacted)
        self.assertIn("MSG00001", redacted)
        self.assertIn("|P|2.5", redacted)

    def test_pii_segments_masked(self):
        redacted = redact_hl7_message(self._adt_message())

        for pii in ("SMITH", "JOHN", "19870101", "123456", "CARDIFF", "CF10 1AA", "JANE", "WARD"):
            self.assertNotIn(pii, redacted)

    def test_segment_structure_preserved(self):
        redacted = redact_hl7_message(self._adt_message())
        segments = redacted.split("\r")

        # Segment identifiers remain visible for debugging.
        self.assertEqual([seg[:3] for seg in segments], ["MSH", "PID", "NK1", "PV1"])
        # PID field values are masked but positions preserved.
        self.assertTrue(segments[1].startswith(f"PID|{REDACTION_MASK}|"))

    def test_empty_fields_left_empty(self):
        redacted = redact_hl7_message("MSH|^~\\&|APP|FAC|RCV|RFAC|20250101||ADT^A28|ID1|P|2.5\rPID|1||||SMITH")
        pid = redacted.split("\r")[1]

        # The empty PID.3/PID.4/PID.5 fields stay empty; the populated name is masked.
        self.assertEqual(pid, f"PID|{REDACTION_MASK}||||{REDACTION_MASK}")

    def test_newline_separated_segments_supported(self):
        redacted = redact_hl7_message(
            "MSH|^~\\&|APP|FAC|RCV|RFAC|20250101||ADT^A28|ID1|P|2.5\nPID|1||123456||SMITH^JOHN"
        )

        self.assertIn("ADT^A28", redacted)
        self.assertNotIn("SMITH", redacted)
        self.assertNotIn("123456", redacted)

    def test_non_hl7_content_fully_masked(self):
        self.assertEqual(redact_hl7_message("This is plain text, not HL7"), REDACTION_MASK)
        self.assertEqual(redact_hl7_message("Binary\x00\x01data"), REDACTION_MASK)

    def test_empty_and_whitespace_returned_unchanged(self):
        self.assertEqual(redact_hl7_message(""), "")
        self.assertEqual(redact_hl7_message("   "), "   ")

    def test_custom_field_separator_respected(self):
        redacted = redact_hl7_message("MSH#^~\\&#APP#FAC#RCV#RFAC#20250101##ADT^A28#ID1#P#2.5#\rPID#1#SMITH")

        self.assertIn("ADT^A28", redacted)
        self.assertNotIn("SMITH", redacted)


if __name__ == "__main__":
    unittest.main()
