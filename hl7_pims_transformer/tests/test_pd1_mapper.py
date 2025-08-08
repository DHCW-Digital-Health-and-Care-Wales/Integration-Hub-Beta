import unittest

from hl7apy.core import Message
from hl7apy.parser import parse_message

from hl7_pims_transformer.mappers.pd1_mapper import map_pd1
from hl7_pims_transformer.utils.field_utils import get_hl7_field_value


class TestPD1Mapper(unittest.TestCase):
    def setUp(self) -> None:
        self.base_hl7_message = (
            "MSH|^~\\&|PIMS|BroMor HL7Sender|EMPI|EMPI|20241231101053+0000||ADT^A08^ADT_A01|48209024|P|2.3.1\r"
            "PD1||||G9310201~W98006\r"
        )
        self.original_message = parse_message(self.base_hl7_message)
        self.new_message = Message(version="2.5")

    def test_map_pd1_pd1_3_and_pd_1_4_for_matching_trigger_event(self) -> None:
        trigger_events = ["A04", "A08"]

        for trigger_event in trigger_events:
            with self.subTest(original_value=trigger_event):
                original_pd1_4_rep2_xcn_1_value = "W98006"
                self.original_message.msh.msh_9.msg_2 = trigger_event
                self.original_message.pd1.pd1_4[0].xcn_1 = "G9310201"
                self.original_message.pd1.pd1_4[1].xcn_1 = original_pd1_4_rep2_xcn_1_value

                map_pd1(self.original_message, self.new_message)

                self.assertEqual(
                    get_hl7_field_value(self.original_message.pd1, "pd1_4.xcn_1"),
                    get_hl7_field_value(self.new_message.pd1, "pd1_4.xcn_1"),
                )
                self.assertEqual(self.new_message.pd1.pd1_3.xon_3.value, original_pd1_4_rep2_xcn_1_value)

    def test_map_pd1_pd1_3_and_pd_1_4_for_non_matching_trigger_event(self) -> None:
        self.original_message.msh.msh_9.msg_2.value = "A40"

        self.original_message.pd1.pd1_4[0].xcn_1 = "G9310201"
        self.original_message.pd1.pd1_4[1].xcn_1 = "W98006"

        map_pd1(self.original_message, self.new_message)

        self.assertEqual(get_hl7_field_value(self.new_message.pd1, "pd1_4.xcn_1"), "")
        self.assertEqual(self.new_message.pd1.pd1_3.xon_3.value, "")
