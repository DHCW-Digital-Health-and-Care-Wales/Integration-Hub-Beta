import unittest

from hl7apy.core import Message
from hl7apy.parser import parse_message

from training_hl7_transformer.mappers.evn_mapper import map_evn


class TestEvnMapper(unittest.TestCase):

    def setUp(self) -> None:
        """
        Set up test fixtures before each test method.
        """
        # Sample HL7 message with EVN segment
        self.hl7_message = (
            "MSH|^~\\&|169|FAC|RECV|RECV_FAC|20260122143055||ADT^A31|MSG001|P|2.3.1\r"
            "EVN|A31|20260122143055|||USER001\r"
        )
        self.original_message = parse_message(self.hl7_message)
        self.new_message = Message(version="2.3.1")

    def test_map_evn_all_direct_mappings(self) -> None:
        map_evn(self.original_message, self.new_message)

        original_evn_str = self.original_message.evn.to_er7() # type: ignore
        new_evn_str = self.new_message.evn.to_er7() # type: ignore
        self.assertEqual(original_evn_str, new_evn_str)
