import unittest

from hl7apy.core import Message
from hl7apy.parser import parse_message

from hl7_chemo_transformer.mappers.evn_mapper import map_evn


class TestEVNMapper(unittest.TestCase):
    def setUp(self) -> None:
        self.base_hl7_message = (
            "MSH|^~\\&|192|192|200|200|20250624161510||ADT^A31|369913945290925|P|2.4|||NE|NE\r"
            "EVN|Sub|20250624161510\r"
        )
        self.original_message = parse_message(self.base_hl7_message)
        self.new_message = Message(version="2.5")

    def test_map_evn_all_direct_mappings(self) -> None:
        map_evn(self.original_message, self.new_message)

        original_evn_str = self.original_message.evn.to_er7()
        new_evn_str = self.new_message.evn.to_er7()
        self.assertEqual(original_evn_str, new_evn_str)


if __name__ == "__main__":
    unittest.main()
