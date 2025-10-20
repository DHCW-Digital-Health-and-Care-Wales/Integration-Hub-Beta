import unittest

from field_utils_lib import get_hl7_field_value
from hl7apy.core import Message
from hl7apy.parser import parse_message

from hl7_phw_transformer.mappers.additional_segment_mapper import map_non_specific_segments


class TestAdditionalSegmentMapper(unittest.TestCase):
    def setUp(self) -> None:
        self.base_hl7_message = (
            "MSH|^~\\&|PHW|PHW HL7Sender|EMPI|EMPI|2024-12-31 10:10:53||ADT^A08^ADT_A01|48209024|P|2.3.1\r"
            'PID|||^03^^^NI~N5022039^^^^PI||TESTER^TEST^""^^MRS.||20000101+^D|F|||'
            "MORRISTON HOSPITAL^HEOL MAES EGLWYS^CWMRHYDYCEIRW^SWANSEASWANSEA^SA6 6NL||"
            "01234567892^PRN^PH~01234567896^ORN^CP|^WPN^PH||M||||||1|||||||^D||||2024-12-31\r"
            "PV1||I|WARD01^BEDS01^1||||123456^DOCTOR^JOHN^^^^DR||456789^NURSE^JANE^^^^RN|||||||ADM|||2024-12-31\r"
            "OBR|1|||12345^CHEST X-RAY||2024-12-31|||||||||789012^TECH^RADIOLOGY^^^^TECH\r"
            "OBX|1|ST|OBS001^OBSERVATION||NORMAL||N|||F||||2024-12-31\r"
        )
        self.original_message = parse_message(self.base_hl7_message)
        self.new_message = Message(version="2.5")

    def test_map_non_specific_segments_copies_additional_segments(self) -> None:
        map_non_specific_segments(self.original_message, self.new_message)

        # Should copy PV1, OBR, OBX segments but not MSH or PID
        self.assertFalse(hasattr(self.new_message, 'msh'))
        self.assertFalse(hasattr(self.new_message, 'pid'))

        self.assertTrue(hasattr(self.new_message, 'pv1'))
        pv1 = self.new_message.pv1
        self.assertEqual(get_hl7_field_value(pv1, "pv1_1"), "1")
        self.assertEqual(get_hl7_field_value(pv1, "pv1_2"), "")
        self.assertEqual(get_hl7_field_value(pv1, "pv1_3.xon_1"), "WARD01")
        self.assertEqual(get_hl7_field_value(pv1, "pv1_3.xon_2"), "BEDS01")
        self.assertEqual(get_hl7_field_value(pv1, "pv1_3.xon_3"), "1")

    def test_map_non_specific_segments_copies_obr_segment(self) -> None:
        map_non_specific_segments(self.original_message, self.new_message)

        self.assertTrue(hasattr(self.new_message, 'obr'))
        obr = self.new_message.obr
        self.assertEqual(get_hl7_field_value(obr, "obr_1"), "1")
        self.assertEqual(get_hl7_field_value(obr, "obr_4.ce_1"), "12345")
        self.assertEqual(get_hl7_field_value(obr, "obr_4.ce_2"), "CHEST X-RAY")

    def test_map_non_specific_segments_copies_obx_segment(self) -> None:
        map_non_specific_segments(self.original_message, self.new_message)

        self.assertTrue(hasattr(self.new_message, 'obx'))
        obx = self.new_message.obx
        self.assertEqual(get_hl7_field_value(obx, "obx_1"), "1")
        self.assertEqual(get_hl7_field_value(obx, "obx_2"), "ST")
        self.assertEqual(get_hl7_field_value(obx, "obx_3.ce_1"), "OBS001")
        self.assertEqual(get_hl7_field_value(obx, "obx_3.ce_2"), "OBSERVATION")
        self.assertEqual(get_hl7_field_value(obx, "obx_5"), "NORMAL")

    def test_map_non_specific_segments_skips_empty_fields(self) -> None:
        map_non_specific_segments(self.original_message, self.new_message)

        pv1 = self.new_message.pv1
        self.assertEqual(get_hl7_field_value(self.original_message.pv1, "pv1_2"), "")
        self.assertEqual(get_hl7_field_value(pv1, "pv1_2"), "")

    def test_map_non_specific_segments_handles_multiple_segments(self) -> None:
        map_non_specific_segments(self.original_message, self.new_message)

        segments = [segment.name for segment in self.new_message.children]
        self.assertIn('PV1', segments)
        self.assertIn('OBR', segments)
        self.assertIn('OBX', segments)

        non_msh_pid_segments = [s for s in self.original_message.children if s.name not in ['MSH', 'PID']]
        self.assertEqual(len([s for s in self.new_message.children]), len(non_msh_pid_segments))

    def test_map_non_specific_segments_empty_message(self) -> None:
        minimal_message = parse_message(
            "MSH|^~\\&|PHW|PHW HL7Sender|EMPI|EMPI|2024-12-31 10:10:53||ADT^A08^ADT_A01|48209024|P|2.3.1\r"
            'PID|||12345||TESTER^TEST\r'
        )
        new_message = Message(version="2.5")

        map_non_specific_segments(minimal_message, new_message)

        self.assertEqual(len([s for s in new_message.children]), 0)


if __name__ == "__main__":
    unittest.main()
