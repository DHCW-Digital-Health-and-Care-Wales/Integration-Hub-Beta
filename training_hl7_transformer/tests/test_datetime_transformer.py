"""
===========================================================================
WEEK 2 EXERCISE 4 SOLUTION: Unit Tests for DateTime Transformer
===========================================================================

This module contains unit tests for the datetime transformation functions.

PRODUCTION REFERENCE:
--------------------
See hl7_phw_transformer/tests/ for similar datetime test patterns.
"""

import unittest

from training_hl7_transformer.datetime_transformer import (
    transform_datetime_to_hl7,
    transform_datetime_to_readable,
)


class TestDatetimeToReadable(unittest.TestCase):
    """
    Test suite for transform_datetime_to_readable function.

    This function converts:
    - From: YYYYMMDDHHMMSS (HL7 compact)
    - To:   YYYY-MM-DD HH:MM:SS (human readable)
    """

    def test_transforms_compact_to_readable(self) -> None:
        """
        Test basic transformation from HL7 compact to readable format.
        """
        # Arrange
        compact = "20260122143055"

        # Act
        result = transform_datetime_to_readable(compact)

        # Assert
        self.assertEqual(result, "2026-01-22 14:30:55")

    def test_returns_none_for_empty_input(self) -> None:
        """
        Test that empty string returns None.
        """
        # Act & Assert
        self.assertIsNone(transform_datetime_to_readable(""))
        self.assertIsNone(transform_datetime_to_readable(None))  # type: ignore

    def test_already_readable_remains_unchanged(self) -> None:
        """
        Test that already-formatted datetime is returned unchanged.
        """
        # Arrange
        readable = "2026-01-22 14:30:55"

        # Act
        result = transform_datetime_to_readable(readable)

        # Assert
        self.assertEqual(result, readable)

    def test_raises_on_invalid_format(self) -> None:
        """
        Test that invalid datetime format raises ValueError.
        """
        # Arrange
        invalid = "not-a-datetime"

        # Act & Assert
        with self.assertRaises(ValueError):
            transform_datetime_to_readable(invalid)

    def test_handles_various_dates(self) -> None:
        """
        Test transformation with various datetime values.
        """
        test_cases = [
            ("20260101000000", "2026-01-01 00:00:00"),  # Midnight on New Year
            ("20261231235959", "2026-12-31 23:59:59"),  # End of year
            ("20260229120000", "2026-02-29 12:00:00"),  # Leap year date (2026 is not leap year - this should fail)
        ]

        for compact, expected in test_cases[:2]:  # Skip leap year test if 2026 isn't leap
            with self.subTest(compact=compact):
                result = transform_datetime_to_readable(compact)
                self.assertEqual(result, expected)


class TestDatetimeToHL7(unittest.TestCase):
    """
    Test suite for transform_datetime_to_hl7 function.

    This function converts:
    - From: YYYY-MM-DD HH:MM:SS (human readable)
    - To:   YYYYMMDDHHMMSS (HL7 compact)

    This is the REVERSE of transform_datetime_to_readable.
    """

    def test_transforms_readable_to_compact(self) -> None:
        """
        Test basic transformation from readable to HL7 compact format.
        """
        # Arrange
        readable = "2026-01-22 14:30:55"

        # Act
        result = transform_datetime_to_hl7(readable)

        # Assert
        self.assertEqual(result, "20260122143055")

    def test_returns_none_for_empty_input(self) -> None:
        """
        Test that empty string returns None.
        """
        # Act & Assert
        self.assertIsNone(transform_datetime_to_hl7(""))

    def test_already_compact_remains_unchanged(self) -> None:
        """
        Test that already-compact datetime is returned unchanged.
        """
        # Arrange
        compact = "20260122143055"

        # Act
        result = transform_datetime_to_hl7(compact)

        # Assert
        self.assertEqual(result, compact)

    def test_roundtrip_transformation(self) -> None:
        """
        Test that transforming to readable and back gives original value.
        """
        # Arrange
        original = "20260122143055"

        # Act: Convert to readable, then back to HL7
        readable = transform_datetime_to_readable(original)
        assert readable is not None, "Expected readable datetime, got None"
        back_to_hl7 = transform_datetime_to_hl7(readable)

        # Assert: Should match original
        self.assertEqual(back_to_hl7, original)


if __name__ == "__main__":
    unittest.main()
