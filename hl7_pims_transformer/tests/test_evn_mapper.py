import unittest

from hl7apy.core import Message
from hl7apy.parser import parse_message

from hl7_pims_transformer.mappers.evn_mapper import map_evn
from hl7_pims_transformer.utils.field_utils import get_hl7_field_value


class TestEVNMapper(unittest.TestCase):
    def setUp(self) -> None:
        self.base_hl7_message = (
            "MSH|^~\\&|PIMS|BroMor HL7Sender|EMPI|EMPI|20250702085450+0000||ADT^A04^ADT_A01|73726643|P|2.3.1\r"
            "EVN||20250702085440+0000||||20250702085440+0000\r"
        )
        self.original_message = parse_message(self.base_hl7_message)
        self.new_message = Message(version="2.5")

    def test_map_evn_1_only(self) -> None:
        map_evn(self.original_message, self.new_message)

        self.assertEqual(
            get_hl7_field_value(self.original_message.evn, "evn_1"),
            get_hl7_field_value(self.new_message.evn, "evn_1"),
        )
