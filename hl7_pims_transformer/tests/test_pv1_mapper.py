import unittest

from hl7apy.core import Message
from hl7apy.parser import parse_message

from hl7_pims_transformer.mappers.pv1_mapper import map_pv1
from hl7_pims_transformer.utils.field_utils import get_hl7_field_value


class TestPV1Mapper(unittest.TestCase):
    def setUp(self) -> None:
        self.base_hl7_message = (
            "MSH|^~\\&|PIMS|BroMor HL7Sender|EMPI|EMPI|20241231101053+0000||ADT^A08^ADT_A01|48209024|P|2.3.1\r"
            "PD1||||G9310201~W98006\r"
            "PV1||NA\r"
        )
        self.original_message = parse_message(self.base_hl7_message)
        self.new_message = Message(version="2.5")

    def test_map_pv1_2_for_matching_trigger_event(self) -> None:
        trigger_events = ["A04", "A08"]

        for trigger_event in trigger_events:
            with self.subTest(original_value=trigger_event):
                # Fresh instances for each subtest iteration
                original_message = parse_message(self.base_hl7_message)
                new_message = Message(version="2.5")

                original_message.msh.msh_9.msg_2 = trigger_event

                map_pv1(original_message, new_message)

                self.assertEqual(new_message.pv1.pv1_2.value, "N")

    def test_map_pv1_2_for_non_matching_trigger_event(self) -> None:
        self.original_message.msh.msh_9.msg_2.value = "A40"

        map_pv1(self.original_message, self.new_message)

        self.assertEqual(get_hl7_field_value(self.new_message.pv1, "pv1_2"), "")
