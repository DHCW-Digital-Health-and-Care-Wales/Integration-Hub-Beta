"""
===========================================================================
WEEK 2 EXERCISE 4 SOLUTION: Unit Tests for PID Mapper
===========================================================================

This module contains unit tests for the PID (Patient Identification) segment mapper.

PRODUCTION REFERENCE:
--------------------
See hl7_phw_transformer/tests/test_pid_mapper.py for production examples.
"""

import unittest

from field_utils_lib import get_hl7_field_value  # type: ignore[import-untyped]
from hl7apy.core import Message  # type: ignore[import-untyped]
from hl7apy.parser import parse_message  # type: ignore[import-untyped]

from training_hl7_transformer.mappers.pid_mapper import map_pid


class TestPIDMapper(unittest.TestCase):
    """
    Test suite for the PID segment mapper.

    Tests cover:
    1. Bulk field copying (PID-1 through PID-39)
    2. Patient name uppercasing (PID-5)
    3. Return value structure
    """

    def setUp(self) -> None:
        """
        Set up test fixtures before each test method.
        """
        # Sample HL7 message with PID segment
        # PID-5 contains: SMITH^John^William^^Mr
        self.hl7_message = (
            "MSH|^~\\&|169|FAC|RECV|RECV_FAC|20260122143055||ADT^A31|MSG001|P|2.3.1\r"
            "PID|||12345678^^^HOSPITAL^MRN||Smith^John^William^^Mr||19850315|M|||"
            "123 Main Street^^Cardiff^Wales^CF10 1AA^^H\r"
        )
        self.original_message = parse_message(self.hl7_message)
        self.new_message = Message(version="2.3.1")

    def test_map_pid_copies_patient_id(self) -> None:
        """
        Test that PID-3 (Patient Identifier List) is copied correctly.
        """
        # Act
        map_pid(self.original_message, self.new_message)

        # Assert
        original_pid3 = get_hl7_field_value(self.original_message.pid, "pid_3")
        new_pid3 = get_hl7_field_value(self.new_message.pid, "pid_3")
        self.assertEqual(original_pid3, new_pid3)

    def test_map_pid_copies_date_of_birth(self) -> None:
        """
        Test that PID-7 (Date/Time of Birth) is copied correctly.
        """
        # Act
        map_pid(self.original_message, self.new_message)

        # Assert
        original_pid7 = get_hl7_field_value(self.original_message.pid, "pid_7")
        new_pid7 = get_hl7_field_value(self.new_message.pid, "pid_7")
        self.assertEqual(original_pid7, new_pid7)

    def test_map_pid_copies_sex(self) -> None:
        """
        Test that PID-8 (Administrative Sex) is copied correctly.
        """
        # Act
        map_pid(self.original_message, self.new_message)

        # Assert
        original_pid8 = get_hl7_field_value(self.original_message.pid, "pid_8")
        new_pid8 = get_hl7_field_value(self.new_message.pid, "pid_8")
        self.assertEqual(original_pid8, new_pid8)

    def test_map_pid_uppercases_patient_name(self) -> None:
        """
        Test that PID-5 (Patient Name) is transformed to uppercase.

        This is the key transformation tested here:
        - Original: Smith^John^William
        - Expected: SMITH^JOHN^WILLIAM
        """
        # Act
        result = map_pid(self.original_message, self.new_message)

        # Assert: Return value should show transformation
        self.assertEqual(result["original_name"], "Smith^John^William")
        self.assertEqual(result["transformed_name"], "SMITH^JOHN^WILLIAM")

    def test_map_pid_uppercases_family_name_component(self) -> None:
        """
        Test that the family name component (XPN-1) is uppercased in the message.
        """
        # Act
        map_pid(self.original_message, self.new_message)

        # Assert: Check the actual field value in the new message
        # The family name might be at different levels depending on structure
        new_family = get_hl7_field_value(self.new_message.pid, "pid_5.xpn_1.fn_1")
        if not new_family:
            new_family = get_hl7_field_value(self.new_message.pid, "pid_5.xpn_1")

        # Should be uppercased
        self.assertEqual(new_family.upper(), new_family)

    def test_map_pid_returns_transformation_details(self) -> None:
        """
        Test that map_pid returns a dictionary with transformation details.
        """
        # Act
        result = map_pid(self.original_message, self.new_message)

        # Assert
        self.assertIsInstance(result, dict)
        self.assertIn("original_name", result)
        self.assertIn("transformed_name", result)


class TestPIDMapperEdgeCases(unittest.TestCase):
    """
    Test edge cases for the PID mapper.
    """

    def test_map_pid_with_empty_name(self) -> None:
        """
        Test mapping when patient name is empty.
        """
        # Arrange: PID with empty PID-5
        hl7_message = (
            "MSH|^~\\&|169|FAC|RECV|RECV_FAC|20260122143055||ADT^A31|MSG001|P|2.3.1\r"
            "PID|||12345678^^^HOSPITAL^MRN||||19850315|M\r"
        )
        original = parse_message(hl7_message)
        new = Message(version="2.3.1")

        # Act: Should not raise exception
        result = map_pid(original, new)

        # Assert: Should handle empty name gracefully
        self.assertEqual(result["original_name"], "")
        self.assertEqual(result["transformed_name"], "")

    def test_map_pid_with_family_name_only(self) -> None:
        """
        Test mapping when only family name is present (no given/middle).
        """
        # Arrange
        hl7_message = (
            "MSH|^~\\&|169|FAC|RECV|RECV_FAC|20260122143055||ADT^A31|MSG001|P|2.3.1\r"
            "PID|||12345678^^^HOSPITAL^MRN||Jones|||19850315|M\r"
        )
        original = parse_message(hl7_message)
        new = Message(version="2.3.1")

        # Act
        result = map_pid(original, new)

        # Assert
        self.assertEqual(result["original_name"], "Jones")
        self.assertEqual(result["transformed_name"], "JONES")

    def test_map_pid_with_special_characters_in_name(self) -> None:
        """
        Test mapping when name contains special characters.
        """
        # Arrange: Name with hyphen and apostrophe
        hl7_message = (
            "MSH|^~\\&|169|FAC|RECV|RECV_FAC|20260122143055||ADT^A31|MSG001|P|2.3.1\r"
            "PID|||12345678^^^HOSPITAL^MRN||O'Brien-Smith^Mary-Jane|||19850315|F\r"
        )
        original = parse_message(hl7_message)
        new = Message(version="2.3.1")

        # Act
        result = map_pid(original, new)

        # Assert: Special characters should be preserved, case changed
        self.assertIn("O'BRIEN-SMITH", result["transformed_name"])
        self.assertIn("MARY-JANE", result["transformed_name"])


if __name__ == "__main__":
    unittest.main()
