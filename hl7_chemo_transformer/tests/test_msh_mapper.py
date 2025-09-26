import unittest

from field_utils_lib import get_hl7_field_value
from hl7apy.core import Message
from hl7apy.parser import parse_message

from hl7_chemo_transformer.mappers.msh_mapper import map_msh


class TestMSHMapper(unittest.TestCase):
    def setUp(self) -> None:
        self.msh_header = "MSH|^~\\&|192|192|200|200|20250701154910||ADT^A28|474997159036153|P|2.4|||NE|NE\r"
        self.original_message = parse_message(self.msh_header)

        self.new_message = Message(version="2.5")

    def test_map_msh_all_transformed_mappings(self) -> None:
        map_msh(self.original_message, self.new_message)

        test_cases = [
            ("msh_9.msg_3", "ADT_A05"),
            ("msh_9", "ADT^A28^ADT_A05"),
            ("msh_12.vid_1", "2.5"),
        ]
        for field_path, expected_value in test_cases:
            self.assertEqual(expected_value, get_hl7_field_value(self.new_message.msh, field_path))

    def test_map_msh_all_direct_mappings(self) -> None:
        map_msh(self.original_message, self.new_message)

        test_cases = [
            "msh_1",
            "msh_2",
            "msh_3.hd_1",
            "msh_4.hd_1",
            "msh_5.hd_1",
            "msh_6.hd_1",
            "msh_7.ts_1",
            "msh_8",
            "msh_9.msg_1",
            "msh_9.msg_2",
            "msh_10",
            "msh_11",
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
