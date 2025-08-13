import unittest

from hl7apy.core import Message
from hl7apy.parser import parse_message

from hl7_pims_transformer.mappers.pid_mapper import map_pid
from hl7_pims_transformer.utils.field_utils import get_hl7_field_value


class TestPIDMapper(unittest.TestCase):
    def setUp(self) -> None:
        self.base_hl7_message = (
            "MSH|^~\\&|PIMS|BroMor HL7Sender|EMPI|EMPI|20241231101053+0000||ADT^A08^ADT_A01|48209024|P|2.3.1\r"
            'PID|||^03^^^NI~N5022039^^^^PI||TESTER^TEST^""^^MRS.||20000101+^D|F|||'
            "MORRISTON HOSPITAL^HEOL MAES EGLWYS^CWMRHYDYCEIRW^SWANSEASWANSEA^SA6 6NL||"
            "01234567892^PRN^PH~01234567896^ORN^CP|^WPN^PH||M||||||1|||||||^D||||20241231101035+0000\r"
        )
        self.original_message = parse_message(self.base_hl7_message)
        self.new_message = Message(version="2.5")

    def test_map_pid_all_direct_mappings(self) -> None:
        map_pid(self.original_message, self.new_message)

        test_cases = [
            "pid_5.xpn_1.fn_1",
            "pid_5.xpn_2",
            "pid_5.xpn_3",
            "pid_5.xpn_4",
            "pid_5.xpn_5",
            "pid_8",
            "pid_11.xad_1",
            "pid_11.xad_2",
            "pid_11.xad_3",
            "pid_11.xad_4",
            "pid_11.xad_5",
            "pid_14.xtn_1",
        ]

        for field_path in test_cases:
            self.assertEqual(
                get_hl7_field_value(self.original_message.pid, field_path),
                get_hl7_field_value(self.new_message.pid, field_path),
            )

    def test_map_pid_3_with_both_repetition(self) -> None:
        self.original_message.pid.pid_3[0].value = "1000000001^03^^^NI"
        self.original_message.pid.pid_3[1].value = "N5022039^^^^PI"

        map_pid(self.original_message, self.new_message)

        new_pid3_rep1 = self.new_message.pid.pid_3[0]
        self.assertEqual(get_hl7_field_value(new_pid3_rep1, "cx_1"), "1000000001")
        self.assertEqual(get_hl7_field_value(new_pid3_rep1, "cx_4.hd_1"), "NHS")
        self.assertEqual(get_hl7_field_value(new_pid3_rep1, "cx_5"), "NH")

        new_pid3_rep2 = self.new_message.pid.pid_3[1]
        self.assertEqual(get_hl7_field_value(new_pid3_rep2, "cx_1"), "N5022039")
        self.assertEqual(get_hl7_field_value(new_pid3_rep2, "cx_4.hd_1"), "103")
        self.assertEqual(get_hl7_field_value(new_pid3_rep2, "cx_5"), "PI")

        self.assertIn("|1000000001^^^NHS^NH~N5022039^^^103^PI|", self.new_message.pid.value)

    def test_map_pid_3_with_an_empty_first_repetition(self) -> None:
        map_pid(self.original_message, self.new_message)

        new_pid3_rep1 = self.new_message.pid.pid_3[0].value
        self.assertEqual(new_pid3_rep1, "")

        new_pid3_rep2 = self.new_message.pid.pid_3[1]
        self.assertEqual(get_hl7_field_value(new_pid3_rep2, "cx_1"), "N5022039")
        self.assertEqual(get_hl7_field_value(new_pid3_rep2, "cx_4.hd_1"), "103")
        self.assertEqual(get_hl7_field_value(new_pid3_rep2, "cx_5"), "PI")

        self.assertIn("|~N5022039^^^103^PI|", self.new_message.pid.value)

    def test_map_pid_3_with_only_first_repetition(self) -> None:
        self.original_message.pid.pid_3[0].value = "1000000001^03^^^NI"
        # second rep does not meet the conditions for mapping
        self.original_message.pid.pid_3[1].value = "1000000001^^^^NH"

        map_pid(self.original_message, self.new_message)

        new_pid3_rep1 = self.new_message.pid.pid_3[0]
        self.assertEqual(get_hl7_field_value(new_pid3_rep1, "cx_1"), "1000000001")
        self.assertEqual(get_hl7_field_value(new_pid3_rep1, "cx_4.hd_1"), "NHS")
        self.assertEqual(get_hl7_field_value(new_pid3_rep1, "cx_5"), "NH")

        self.assertIn("|1000000001^^^NHS^NH|", self.new_message.pid.value)

    def test_map_pid_3_missing_pid_3(self) -> None:
        self.original_message.pid.pid_3[0].value = ""
        self.original_message.pid.pid_3[1].value = ""

        map_pid(self.original_message, self.new_message)

        self.assertEqual(self.new_message.pid.pid_3.value, "")

    def test_map_pid_13_repetitions(self) -> None:
        map_pid(self.original_message, self.new_message)

        original_pid13_reps = getattr(self.original_message.pid, "pid_13")
        new_pid13_reps = getattr(self.new_message.pid, "pid_13")

        self.assertEqual(len(original_pid13_reps), len(new_pid13_reps))

        for rep_count in range(len(original_pid13_reps)):
            self.assertEqual(
                get_hl7_field_value(original_pid13_reps[rep_count], "xtn_1"),
                get_hl7_field_value(new_pid13_reps[rep_count], "xtn_1"),
            )

    def test_map_pid_29_ts1_datetime_trimming(self) -> None:
        test_cases = [
            ("20250630155034+0000", "20250630155034"),  # length > 6, trimmed
            ("2025063015+0000", "2025063015"),  # length > 6, trimmed
            ("20250630+0100", "20250630"),  # length > 6, trimmed
            ("202506", '""'),  # length = 6, set to empty
            ("20250", '""'),  # length < 6, set to empty
            ('""', '""'),  # empty string
            ("", '""'),  # no value
            ("20250630155034-0100", "20250630155034-0100"),  # negative timezone, shouldn't happen in GB
        ]

        for original_value, expected_value in test_cases:
            with self.subTest(original_value=original_value):
                self.original_message.pid.pid_29.ts_1.value = original_value

                map_pid(self.original_message, self.new_message)

                self.assertEqual(get_hl7_field_value(self.new_message.pid, "pid_29.ts_1"), expected_value)
