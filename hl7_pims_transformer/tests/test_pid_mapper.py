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
