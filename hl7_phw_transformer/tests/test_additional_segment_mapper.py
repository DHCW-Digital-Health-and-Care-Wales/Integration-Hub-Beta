import unittest

from field_utils_lib import get_hl7_field_value
from hl7apy.core import Message
from hl7apy.parser import parse_message

from hl7_phw_transformer.mappers.additional_segment_mapper import map_non_specific_segments


class TestAdditionalSegmentMapper(unittest.TestCase):
    def setUp(self) -> None:
        self.base_hl7_message = (
            "MSH|^~\\&|252|252|100|100|2025-05-05 23:23:32||ADT^A31^ADT_A05|202505052323364444444444|P|2.5|||||GBR||EN\r"
            "EVN||20250502092900|20250505232332|||20250505232332\r"
            "PID|||8888888^^^252^PI~4444444444^^^NHS^NH||MYSURNAME^MYFNAME^MYMNAME^^MR||19990101|M|^^||99, MY ROAD^MY PLACE^MY CITY^MY COUNTY^SA99 1XX^^H~^^^^^^||^^^~|||||||||||||||||||01\r"
            "PD1|||^^W00000^|G999999\r"
            "PV1||U\r"
        )
        self.original_message = parse_message(self.base_hl7_message)
        self.new_message = Message(version="2.5")

    def test_map_non_specific_segments_copies_additional_segments(self) -> None:
        map_non_specific_segments(self.original_message, self.new_message)

        segments = [s.name for s in self.new_message.children]
        self.assertNotIn('PID', segments)

        self.assertTrue(hasattr(self.new_message, 'evn'))
        self.assertTrue(hasattr(self.new_message, 'pd1'))
        self.assertTrue(hasattr(self.new_message, 'pv1'))
        
        evn = self.new_message.evn
        self.assertEqual(get_hl7_field_value(evn, "evn_2"), "20250502092900")
        
        pv1 = self.new_message.pv1
        self.assertEqual(get_hl7_field_value(pv1, "pv1_2"), "U")

    def test_map_non_specific_segments_copies_pd1_segment(self) -> None:
        map_non_specific_segments(self.original_message, self.new_message)

        self.assertTrue(hasattr(self.new_message, 'pd1'))
        pd1 = self.new_message.pd1
        self.assertEqual(get_hl7_field_value(pd1, "pd1_4"), "G999999")

    def test_map_non_specific_segments_copies_evn_segment(self) -> None:
        map_non_specific_segments(self.original_message, self.new_message)

        self.assertTrue(hasattr(self.new_message, 'evn'))
        evn = self.new_message.evn
        self.assertEqual(get_hl7_field_value(evn, "evn_2"), "20250502092900")
        self.assertEqual(get_hl7_field_value(evn, "evn_3"), "20250505232332")
        self.assertEqual(get_hl7_field_value(evn, "evn_6"), "20250505232332")

    def test_map_non_specific_segments_skips_empty_fields(self) -> None:
        map_non_specific_segments(self.original_message, self.new_message)

        pv1 = self.new_message.pv1
        self.assertEqual(get_hl7_field_value(self.original_message.pv1, "pv1_1"), "")
        self.assertEqual(get_hl7_field_value(pv1, "pv1_1"), "")

    def test_map_non_specific_segments_handles_multiple_segments(self) -> None:
        map_non_specific_segments(self.original_message, self.new_message)

        segments = [segment.name for segment in self.new_message.children]
        self.assertIn('EVN', segments)
        self.assertIn('PD1', segments)
        self.assertIn('PV1', segments)

        non_msh_pid_segments = [s for s in self.original_message.children if s.name not in ['MSH', 'PID']]
        expected_count = 1 + len(non_msh_pid_segments)  # 1 for auto-created MSH
        self.assertEqual(len([s for s in self.new_message.children]), expected_count)

    def test_map_non_specific_segments_empty_message(self) -> None:
        minimal_message = parse_message(
            "MSH|^~\\&|252|252|100|100|2025-05-05 23:23:32||ADT^A31^ADT_A05|202505052323364444444444|P|2.5|||||GBR||EN\r"
            'PID|||8888888^^^252^PI||MYSURNAME^MYFNAME\r'
        )
        new_message = Message(version="2.5")

        map_non_specific_segments(minimal_message, new_message)

        self.assertEqual(len([s for s in new_message.children]), 1)
        self.assertEqual(new_message.children[0].name, 'MSH')


if __name__ == "__main__":
    unittest.main()
