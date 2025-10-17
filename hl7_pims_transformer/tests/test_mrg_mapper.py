import unittest

from field_utils_lib import get_hl7_field_value
from hl7apy.core import Message
from hl7apy.parser import parse_message

from hl7_pims_transformer.mappers.mrg_mapper import map_mrg
from tests.pims_messages import pims_messages


class TestMRGMapper(unittest.TestCase):
    def setUp(self) -> None:
        self.a40_hl7_message = pims_messages["a40"]
        self.original_message = parse_message(self.a40_hl7_message)
        self.new_message = Message(version="2.5")

    def test_map_mrg_fields_for_non_matching_trigger_event(self) -> None:
        trigger_events = ["A04", "A08"]

        for trigger_event in trigger_events:
            with self.subTest(original_value=trigger_event):
                # Fresh instances for each subtest iteration
                original_message = parse_message(self.a40_hl7_message)
                new_message = Message(version="2.5")

                original_message.msh.msh_9.msg_2 = trigger_event

                map_mrg(original_message, new_message)

                mrg_segment = new_message.mrg
                if mrg_segment is None:
                    self.assertIsNone(mrg_segment)
                else:
                    self.assertEqual(len(mrg_segment), 0)

    def test_map_mrg_fields_for_matching_trigger_event(self) -> None:
        self.original_message.msh.msh_9.msg_2.value = "A40"

        map_mrg(self.original_message, self.new_message)

        self.assertEqual(get_hl7_field_value(self.new_message.mrg, "mrg_1.cx_1"), "00100001")
        self.assertEqual(get_hl7_field_value(self.new_message.mrg, "mrg_1.cx_4.hd_1"), "103")
        self.assertEqual(self.new_message.mrg.mrg_1.cx_5.value, "PI")
