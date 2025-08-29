import unittest

from hl7apy.core import Message
from hl7apy.parser import parse_message

from hl7_pims_transformer.mappers.msh_mapper import map_msh
from hl7_pims_transformer.utils.field_utils import get_hl7_field_value


class TestMSHMapper(unittest.TestCase):
    def setUp(self) -> None:
        self.msh_header = (
            "MSH|^~\\&|PIMS|BroMor HL7Sender|EMPI|EMPI|20241231101053+0000||ADT^A08^ADT_A01|48209024|P|2.3.1\r"
        )
        self.original_message = parse_message(self.msh_header)

        self.new_message = Message(version="2.5")

    def test_map_msh_all_harcoded_mappings(self) -> None:
        map_msh(self.original_message, self.new_message)

        test_cases = [
            ("msh_3.hd_1", "103"),
            ("msh_4.hd_1", "103"),
            ("msh_5.hd_1", "200"),
            ("msh_6.hd_1", "200"),
            ("msh_9.msg_1", "ADT"),
            ("msh_12.vid_1", "2.5"),
            ("msh_17", "GBR"),
            ("msh_19.ce_1", "EN"),
        ]
        for field_path, expected_value in test_cases:
            self.assertEqual(expected_value, get_hl7_field_value(self.new_message.msh, field_path))

    def test_map_msh_all_direct_mappings(self) -> None:
        map_msh(self.original_message, self.new_message)

        test_cases = [
            "msh_1",
            "msh_2",
            "msh_8",
            "msh_10",
            "msh_11",
            "msh_13",
        ]

        for field_path in test_cases:
            self.assertEqual(
                get_hl7_field_value(self.original_message.msh, field_path),
                get_hl7_field_value(self.new_message.msh, field_path),
            )

    def test_msh9_mapping(self) -> None:
        test_cases = [
            ("ADT^A04^ADT_A01", "ADT^A28^ADT_A05"),
            ("ADT^A08^ADT_A01", "ADT^A31^ADT_A05"),
            ("ADT^A40^ADT_A40", "ADT^A40^ADT_A39"),
        ]
        for msh_9_original_value, expected_value in test_cases:
            with self.subTest(msh_9=msh_9_original_value):
                # Fresh instances for each subtest iteration
                original_message = parse_message(self.msh_header)
                new_message = Message(version="2.5")

                original_message.msh.msh_9 = msh_9_original_value

                map_msh(original_message, new_message)

                self.assertEqual(expected_value, get_hl7_field_value(new_message.msh, "msh_9"))
