"""
===========================================================================
WEEK 2 EXERCISE 4 SOLUTION: Unit Tests for EVN Mapper
===========================================================================

This module contains unit tests for the EVN (Event Type) segment mapper.

PRODUCTION REFERENCE:
--------------------
See hl7_pims_transformer/tests/ for similar test patterns.
"""

import unittest

from field_utils_lib import get_hl7_field_value  # type: ignore[import-untyped]
from hl7apy.core import Message  # type: ignore[import-untyped]
from hl7apy.parser import parse_message  # type: ignore[import-untyped]

from training_hl7_transformer.mappers.evn_mapper import map_evn


class TestEVNMapper(unittest.TestCase):
    """
    Test suite for the EVN segment mapper.

    Tests cover:
    1. Bulk field copying (EVN-1 through EVN-7)
    2. Return value structure
    3. Specific field values
    """

    def setUp(self) -> None:
        """
        Set up test fixtures before each test method.
        """
        # Sample HL7 message with EVN segment
        self.hl7_message = (
            "MSH|^~\\&|169|FAC|RECV|RECV_FAC|20260122143055||ADT^A31|MSG001|P|2.3.1\rEVN|A31|20260122143055|||USER001\r"
        )
        self.original_message = parse_message(self.hl7_message)
        self.new_message = Message(version="2.3.1")

    def test_map_evn_copies_all_fields(self) -> None:
        """
        Test that map_evn copies all EVN fields from original to new message.
        """
        # Act
        map_evn(self.original_message, self.new_message)

        # Assert: EVN-1 (Event Type Code) should be copied
        self.assertEqual(
            get_hl7_field_value(self.original_message.evn, "evn_1"),
            get_hl7_field_value(self.new_message.evn, "evn_1"),
        )

        # EVN-5 (Operator ID) should be copied
        self.assertEqual(
            get_hl7_field_value(self.original_message.evn, "evn_5"),
            get_hl7_field_value(self.new_message.evn, "evn_5"),
        )

    def test_map_evn_copies_datetime(self) -> None:
        """
        Test that EVN-2 (Recorded Date/Time) is copied correctly.
        """
        # Act
        map_evn(self.original_message, self.new_message)

        # Assert
        original_evn2 = get_hl7_field_value(self.original_message.evn, "evn_2.ts_1")
        new_evn2 = get_hl7_field_value(self.new_message.evn, "evn_2.ts_1")

        # EVN-2 might be stored at different levels depending on message version
        if not original_evn2:
            original_evn2 = get_hl7_field_value(self.original_message.evn, "evn_2")
        if not new_evn2:
            new_evn2 = get_hl7_field_value(self.new_message.evn, "evn_2")

        self.assertEqual(original_evn2, new_evn2)

    def test_map_evn_returns_details(self) -> None:
        """
        Test that map_evn returns transformation details for logging.
        """
        # Act
        result = map_evn(self.original_message, self.new_message)

        # Assert: Result should be a dictionary with expected keys
        self.assertIsInstance(result, dict)
        self.assertIn("evn_2_recorded_datetime", result)
        self.assertIn("evn_5_operator_id", result)

        # Verify the operator ID value
        self.assertEqual(result["evn_5_operator_id"], "USER001")


class TestEVNMapperEdgeCases(unittest.TestCase):
    """
    Test edge cases for the EVN mapper.
    """

    def test_map_evn_with_minimal_evn(self) -> None:
        """
        Test mapping with a minimal EVN segment (only required fields).
        """
        # Arrange: EVN with only datetime
        hl7_message = "MSH|^~\\&|169|FAC|RECV|RECV_FAC|20260122143055||ADT^A31|MSG001|P|2.3.1\rEVN||20260122143055\r"
        original = parse_message(hl7_message)
        new = Message(version="2.3.1")

        # Act: Should not raise exception
        result = map_evn(original, new)

        # Assert: Result should still have expected keys
        self.assertIn("evn_2_recorded_datetime", result)

    def test_map_evn_with_empty_fields(self) -> None:
        """
        Test mapping when EVN has empty optional fields.
        """
        # Arrange
        hl7_message = "MSH|^~\\&|169|FAC|RECV|RECV_FAC|20260122143055||ADT^A31|MSG001|P|2.3.1\rEVN||20260122143055|||\r"
        original = parse_message(hl7_message)
        new = Message(version="2.3.1")

        # Act
        result = map_evn(original, new)

        # Assert: Empty fields should be handled gracefully
        self.assertEqual(result["evn_5_operator_id"], "")


if __name__ == "__main__":
    unittest.main()
