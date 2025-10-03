import unittest

from field_utils_lib import get_hl7_field_value
from hl7apy.core import Message
from hl7apy.parser import parse_message

from hl7_chemo_transformer.mappers.pd1_mapper import map_pd1


class TestPD1Mapper(unittest.TestCase):
    def setUp(self) -> None:
        self.base_hl7_message = (
            "MSH|^~\\&|192|192|200|200|20250624161510||ADT^A31|369913945290925|P|2.4|||NE|NE\rPD1||||G7000001\r"
        )
        self.original_message = parse_message(self.base_hl7_message)
        self.new_message = Message(version="2.5")

    def test_map_pd1_all_direct_mappings(self) -> None:
        map_pd1(self.original_message, self.new_message)

        test_cases = [
            "pd1_3.xon_1",
            "pd1_3.xon_3",
            "pd1_3.xon_4",
            "pd1_3.xon_5",
            "pd1_3.xon_7",
            "pd1_3.xon_9",
            "pd1_3.xon_6.hd_1",
            "pd1_3.xon_8.hd_1",
            "pd1_4.xcn_1",
            "pd1_4.xcn_2.fn_1",
            "pd1_4.xcn_3",
            "pd1_4.xcn_4",
            "pd1_4.xcn_6",
        ]

        for field_path in test_cases:
            self.assertEqual(
                get_hl7_field_value(self.original_message.pd1, field_path),
                get_hl7_field_value(self.new_message.pd1, field_path),
            )
