import unittest

from field_utils_lib import get_hl7_field_value
from hl7apy.core import Message
from hl7apy.parser import parse_message

from training_hl7_transformer.mappers.msh_mapper import map_msh


class TestMshMapper(unittest.TestCase):

    def setUp(self) -> None:
        self.msh_header = "MSH|^~\\&|169|TRAINING_H|RECEIVER|RECEIVER_FAC|20260115120000||ADT^A31|MSG001|P|2.3.1\r"
        self.original_message = parse_message(self.msh_header)
        self.new_message = Message(version="2.3.1")


    def test_map_msh_all_direct_mappings(self) -> None:
        map_msh(self.original_message, self.new_message)

        test_cases = [
            "msh_3", "msh_4", "msh_5", "msh_6", "msh_8", "msh_9", "msh_10",
            "msh_11", "msh_12", "msh_13", "msh_14", "msh_15", "msh_16",
            "msh_17", "msh_18", "msh_19", "msh_20", "msh_21",
        ]

        for field_path in test_cases:
            self.assertEqual(
                get_hl7_field_value(self.original_message.msh, field_path),
                get_hl7_field_value(self.new_message.msh, field_path),
            )


    def test_map_msh_transforms_datetime_to_readable(self) -> None:
        # Arrange
        original_datetime = get_hl7_field_value(self.original_message.msh, "msh_7.ts_1")
        self.assertEqual(original_datetime, "20260115120000")

        # Act
        result = map_msh(self.original_message, self.new_message)

        # Assert: MSH-7 formatted
        new_datetime = get_hl7_field_value(self.new_message.msh, "msh_7.ts_1")
        self.assertEqual(new_datetime, "2026-01-15 12:00:00")

        # Verify return value
        self.assertEqual(result[0] if result is not None else None, "20260115120000")
        self.assertEqual(result[1] if result is not None else None, "2026-01-15 12:00:00")


    def test_map_msh_empty_datetime(self) -> None:
        # Arrange
        self.original_message.msh.msh_7.ts_1 = ""  # type: ignore

        # Act
        result = map_msh(self.original_message, self.new_message)

        # Assert: MSH-7 should be empty in new message
        self.assertEqual(result[0] if result is not None else None, "")
        self.assertEqual(result[1] if result is not None else None, "")



class TestMshMapperEdgeCases(unittest.TestCase):

    def test_map_msh_with_minimal_messgae(self) -> None:
        # Arrange: Create a minimal MSH segment with only required fields
        minimal_msh = "MSH|^~\\&|169|FAC||FAC|20260122143055||ADT^A31|1|P|2.3.1\r"
        original_message = parse_message(minimal_msh)
        new_message = Message(version="2.3.1")

        # Act
        result = map_msh(original_message, new_message)

        # Assert: Basic transformation should work
        self.assertEqual(result[0] if result is not None else None, "20260122143055" or "")

if __name__ == '__main__':
    unittest.main()
