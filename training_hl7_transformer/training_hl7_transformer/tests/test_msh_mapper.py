import unittest

from field_utils_lib import get_hl7_field_value
from hl7apy.core import Message
from hl7apy.parser import parse_message

from training_hl7_transformer.mappers.msh_mapper import map_msh


class TestMSHMapper(unittest.TestCase):
    def setUp(self) -> None:
        self.msh_header = "MSH|^~\\&|169|HOSPITAL_A|RECEIVER_APP|RECEIVER_FAC|20260122143055||ADT^A31|MSG001|P|2.3.1\r"

        self.original_message = parse_message(self.msh_header)
        self.new_message = Message(version="2.3.1")

    def test_map_msh_copies_standard_fields(self) -> None:
        map_msh(self.original_message, self.new_message)
        self.assertEqual(
                    get_hl7_field_value(self.original_message.msh, "msh_4"),
                    get_hl7_field_value(self.new_message.msh, "msh_4"),
                )
    
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


if __name__ == "__main__":
    unittest.main()