import unittest

from hl7apy.core import Message
from hl7apy.parser import parse_message

from hl7_chemo_transformer.mappers.nk1_mapper import map_nk1
from hl7_chemo_transformer.utils.field_utils import get_hl7_field_value


class TestNK1Mapper(unittest.TestCase):
    def setUp(self) -> None:
        self.base_hl7_message = (
            "MSH|^~\\&|192|192|200|200|20250701154910||ADT^A28|474997159036153|P|2.4|||NE|NE\r"
            "NK1|1|NEXT^OF^KIN^^Mr.|FTH|123 MAIN ST^APT 1^CITY^STATE^ZIP^COUNTRY^M||07000000001^WPN\r"
        )
        self.original_message = parse_message(self.base_hl7_message)
        self.new_message = Message(version="2.5")

    def test_map_nk1_all_direct_mappings(self) -> None:
        map_nk1(self.original_message, self.new_message)

        test_cases = [
            "nk1_2.xpn_1.fn_1",
            "nk1_2.xpn_2",
            "nk1_2.xpn_7",
            "nk1_3.ce_1",
            "nk1_4.xad_1.sad_1",
            "nk1_4.xad_2",
            "nk1_4.xad_7",
            "nk1_5.xtn_1",
        ]

        for field_path in test_cases:
            self.assertEqual(
                get_hl7_field_value(self.original_message.nk1, field_path),
                get_hl7_field_value(self.new_message.nk1, field_path),
            )


if __name__ == "__main__":
    unittest.main()
