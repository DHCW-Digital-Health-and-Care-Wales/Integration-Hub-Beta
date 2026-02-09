"""
===========================================================================
WEEK 2 EXERCISE 4 SOLUTION: Unit Tests for MSH Mapper
===========================================================================

This module contains unit tests for the MSH segment mapper.

EXERCISE REQUIREMENTS:
---------------------
Write unit tests for the MSH mapper following existing test patterns.

PRODUCTION REFERENCE:
--------------------
See hl7_phw_transformer/tests/test_msh_mapper.py for production examples.
"""

import unittest

from field_utils_lib import get_hl7_field_value  # type: ignore[import-untyped]
from hl7apy.core import Message  # type: ignore[import-untyped]
from hl7apy.parser import parse_message  # type: ignore[import-untyped]

from training_hl7_transformer.mappers.msh_mapper import map_msh


class TestMSHMapper(unittest.TestCase):
    """
    Test suite for the MSH segment mapper.

    Tests cover:
    1. Field copying (MSH-3 through MSH-21)
    2. MSH-3 transformation (Sending Application)
    3. MSH-7 datetime transformation (WEEK 2 EXERCISE 1)
    """

    def setUp(self) -> None:
        """
        Set up test fixtures before each test method.

        Creates:
        - A sample HL7 message header string
        - An original message parsed from the header
        - A new empty message to transform into
        """
        # Sample MSH segment with HL7 compact datetime format
        # MSH-7: 20260122143055 (YYYYMMDDHHMMSS format)
        self.msh_header = "MSH|^~\\&|169|HOSPITAL_A|RECEIVER_APP|RECEIVER_FAC|20260122143055||ADT^A31|MSG001|P|2.3.1\r"
        self.original_message = parse_message(self.msh_header)
        self.new_message = Message(version="2.3.1")

    # =========================================================================
    # Test 1: Field Copying
    # =========================================================================
    def test_map_msh_copies_standard_fields(self) -> None:
        """
        Test that map_msh copies all standard MSH fields (3-21).

        This test verifies that the bulk copy operation works correctly
        by checking that key fields match between original and new messages.
        """
        # Act: Apply the MSH mapper
        map_msh(self.original_message, self.new_message)

        # Assert: Key fields should match (except MSH-3 which is transformed)
        # We check a subset of important fields

        # MSH-4: Sending Facility should be copied
        self.assertEqual(
            get_hl7_field_value(self.original_message.msh, "msh_4"),
            get_hl7_field_value(self.new_message.msh, "msh_4"),
        )

        # MSH-5: Receiving Application should be copied
        self.assertEqual(
            get_hl7_field_value(self.original_message.msh, "msh_5"),
            get_hl7_field_value(self.new_message.msh, "msh_5"),
        )

        # MSH-6: Receiving Facility should be copied
        self.assertEqual(
            get_hl7_field_value(self.original_message.msh, "msh_6"),
            get_hl7_field_value(self.new_message.msh, "msh_6"),
        )

        # MSH-9: Message Type should be copied
        self.assertEqual(
            get_hl7_field_value(self.original_message.msh, "msh_9"),
            get_hl7_field_value(self.new_message.msh, "msh_9"),
        )

        # MSH-10: Message Control ID should be copied
        self.assertEqual(
            get_hl7_field_value(self.original_message.msh, "msh_10"),
            get_hl7_field_value(self.new_message.msh, "msh_10"),
        )

        # MSH-11: Processing ID should be copied
        self.assertEqual(
            get_hl7_field_value(self.original_message.msh, "msh_11"),
            get_hl7_field_value(self.new_message.msh, "msh_11"),
        )

        # MSH-12: Version ID should be copied
        self.assertEqual(
            get_hl7_field_value(self.original_message.msh, "msh_12"),
            get_hl7_field_value(self.new_message.msh, "msh_12"),
        )

    # =========================================================================
    # Test 2: MSH-3 Transformation (Sending Application)
    # =========================================================================
    def test_map_msh_transforms_sending_application(self) -> None:
        """
        Test that MSH-3 (Sending Application) is transformed to 'TRAINING_TRANSFORMER'.

        This is our core transformation - changing the sender identity to show
        the message has been processed by our transformer.
        """
        # Act
        result = map_msh(self.original_message, self.new_message)

        # Assert: MSH-3 should be "TRAINING_TRANSFORMER"
        new_msh3 = get_hl7_field_value(self.new_message.msh, "msh_3")
        self.assertEqual(new_msh3, "TRAINING_TRANSFORMER")

        # Also verify the return value contains the transformation details
        self.assertEqual(result["original_sending_app"], "169")
        self.assertEqual(result["new_sending_app"], "TRAINING_TRANSFORMER")

    # =========================================================================
    # Test 3: MSH-7 DateTime Transformation (WEEK 2 EXERCISE 1)
    # =========================================================================
    def test_map_msh_transforms_datetime_to_readable(self) -> None:
        """
        Test that MSH-7 datetime is transformed from YYYYMMDDHHMMSS to YYYY-MM-DD HH:MM:SS.

        This is the WEEK 2 EXERCISE 1 solution - converting HL7 compact datetime
        to a human-readable format.
        """
        # Arrange: Verify original is in compact format
        original_datetime = get_hl7_field_value(self.original_message.msh, "msh_7.ts_1")
        self.assertEqual(original_datetime, "20260122143055")

        # Act
        result = map_msh(self.original_message, self.new_message)

        # Assert: MSH-7 should be in readable format
        new_datetime = get_hl7_field_value(self.new_message.msh, "msh_7.ts_1")
        self.assertEqual(new_datetime, "2026-01-22 14:30:55")

        # Verify return value contains datetime transformation details
        self.assertEqual(result["original_datetime"], "20260122143055")
        self.assertEqual(result["transformed_datetime"], "2026-01-22 14:30:55")

    def test_map_msh_datetime_already_readable(self) -> None:
        """
        Test that if MSH-7 is already in readable format, it remains unchanged.
        """
        # Arrange: Set MSH-7 to already-readable format
        self.original_message.msh.msh_7.ts_1 = "2026-01-22 14:30:55"  # type: ignore[union-attr]

        # Act
        _ = map_msh(self.original_message, self.new_message)

        # Assert: Should remain unchanged
        new_datetime = get_hl7_field_value(self.new_message.msh, "msh_7.ts_1")
        self.assertEqual(new_datetime, "2026-01-22 14:30:55")

    def test_map_msh_empty_datetime(self) -> None:
        """
        Test that empty MSH-7 is handled gracefully.
        """
        # Arrange: Set MSH-7 to empty
        self.original_message.msh.msh_7.ts_1 = ""  # type: ignore[union-attr]

        # Act: Should not raise exception
        result = map_msh(self.original_message, self.new_message)

        # Assert: Return value should have empty datetime fields
        self.assertEqual(result["original_datetime"], "")
        self.assertEqual(result["transformed_datetime"], "")

    # =========================================================================
    # Test 4: Return Value Structure
    # =========================================================================
    def test_map_msh_returns_transformation_details(self) -> None:
        """
        Test that map_msh returns a dictionary with all expected keys.
        """
        # Act
        result = map_msh(self.original_message, self.new_message)

        # Assert: All expected keys should be present
        self.assertIn("original_sending_app", result)
        self.assertIn("new_sending_app", result)
        self.assertIn("original_datetime", result)
        self.assertIn("transformed_datetime", result)

        # All values should be strings
        for key, value in result.items():
            self.assertIsInstance(value, str, f"Expected {key} to be a string")


class TestMSHMapperEdgeCases(unittest.TestCase):
    """
    Test edge cases and error handling for the MSH mapper.
    """

    def test_map_msh_with_minimal_message(self) -> None:
        """
        Test mapping with a minimal MSH segment (only required fields).
        """
        # Arrange: Create a minimal MSH
        minimal_msh = "MSH|^~\\&|169|FAC||FAC|20260122143055||ADT^A31|1|P|2.3.1\r"
        original = parse_message(minimal_msh)
        new = Message(version="2.3.1")

        # Act: Should not raise exception
        result = map_msh(original, new)

        # Assert: Basic transformation should work
        self.assertEqual(result["new_sending_app"], "TRAINING_TRANSFORMER")


if __name__ == "__main__":
    unittest.main()
