import unittest

from field_utils_lib import get_hl7_field_value
from hl7apy.core import Message
from hl7apy.parser import parse_message

from hl7_phw_transformer.mappers.msh_mapper import map_msh


class TestMSHMapper(unittest.TestCase):
    def setUp(self) -> None:
        self.msh_header = (
            "MSH|^~\\&|PHW|PHW HL7Sender|EMPI|EMPI|2024-12-31 10:10:53||ADT^A08^ADT_A01|48209024|P|2.3.1\r"
        )
        self.original_message = parse_message(self.msh_header)
        self.new_message = Message(version="2.5")

    def test_map_msh_all_direct_mappings(self) -> None:
        map_msh(self.original_message, self.new_message)

        test_cases = [
            "msh_3",
            "msh_4",
            "msh_5",
            "msh_6",
            "msh_8",
            "msh_9",
            "msh_10",
            "msh_11",
            "msh_12",
            "msh_13",
            "msh_14",
            "msh_15",
            "msh_16",
            "msh_17",
            "msh_18",
            "msh_19",
            "msh_20",
            "msh_21",
        ]

        for field_path in test_cases:
            self.assertEqual(
                get_hl7_field_value(self.original_message.msh, field_path),
                get_hl7_field_value(self.new_message.msh, field_path),
            )

    def test_map_msh_7_datetime_transformation(self) -> None:
        result = map_msh(self.original_message, self.new_message)

        self.assertEqual(get_hl7_field_value(self.new_message.msh, "msh_7.ts_1"), "20241231101053")
        self.assertEqual(result, ("2024-12-31 10:10:53", "20241231101053"))

    def test_map_msh_7_datetime_already_formatted(self) -> None:
        self.original_message.msh.msh_7.ts_1 = "20241231101053"
        result = map_msh(self.original_message, self.new_message)

        self.assertEqual(get_hl7_field_value(self.new_message.msh, "msh_7.ts_1"), "20241231101053")
        self.assertEqual(result, ("20241231101053", "20241231101053"))

    def test_map_msh_7_no_datetime(self) -> None:
        self.original_message.msh.msh_7.ts_1 = ""
        original_msh7_value = get_hl7_field_value(self.new_message.msh, "msh_7.ts_1")
        result = map_msh(self.original_message, self.new_message)

        # MSH-7 should remain unchanged in the new message (it gets set during Message creation)
        self.assertEqual(get_hl7_field_value(self.new_message.msh, "msh_7.ts_1"), original_msh7_value)
        self.assertIsNone(result)

    def test_map_msh_repeating_fields_are_copied(self) -> None:
        repeating_msh_header = (
            "MSH|^~\\&|PHW~PHW2|PHW HL7Sender|EMPI~EMPI2|EMPI|2024-12-31 10:10:53||"
            "ADT^A08^ADT_A01|48209024|P|2.3.1\r"
        )
        original_message = parse_message(repeating_msh_header)
        new_message = Message(version="2.5")

        map_msh(original_message, new_message)

        # All repetitions for repeating fields should be preserved
        self.assertEqual(
            get_hl7_field_value(original_message.msh, "msh_3"),
            get_hl7_field_value(new_message.msh, "msh_3"),
        )
        self.assertEqual(
            get_hl7_field_value(original_message.msh, "msh_5"),
            get_hl7_field_value(new_message.msh, "msh_5"),
        )


if __name__ == "__main__":
    unittest.main()
