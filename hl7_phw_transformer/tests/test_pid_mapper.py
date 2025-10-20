import unittest

from field_utils_lib import get_hl7_field_value
from hl7apy.core import Message
from hl7apy.parser import parse_message

from hl7_phw_transformer.mappers.pid_mapper import map_pid


class TestPIDMapper(unittest.TestCase):
    def setUp(self) -> None:
        self.base_hl7_message = (
            "MSH|^~\\&|PHW|PHW HL7Sender|EMPI|EMPI|2024-12-31 10:10:53||ADT^A08^ADT_A01|48209024|P|2.3.1\r"
            'PID|||^03^^^NI~N5022039^^^^PI||TESTER^TEST^""^^MRS.||20000101+^D|F|||'
            "MORRISTON HOSPITAL^HEOL MAES EGLWYS^CWMRHYDYCEIRW^SWANSEASWANSEA^SA6 6NL||"
            "01234567892^PRN^PH~01234567896^ORN^CP|^WPN^PH||M||||||1|||||||^D||||2024-12-31\r"
        )
        self.original_message = parse_message(self.base_hl7_message)
        self.new_message = Message(version="2.5")

    def test_map_pid_all_direct_mappings(self) -> None:
        map_pid(self.original_message, self.new_message)

        test_cases = [
            "pid_1",
            "pid_2",
            "pid_3",
            "pid_4",
            "pid_5",
            "pid_6",
            "pid_7",
            "pid_8",
            "pid_9",
            "pid_10",
            "pid_11",
            "pid_12",
            "pid_13",
            "pid_14",
            "pid_15",
            "pid_16",
            "pid_17",
            "pid_18",
            "pid_19",
            "pid_20",
            "pid_21",
            "pid_22",
            "pid_23",
            "pid_24",
            "pid_25",
            "pid_26",
            "pid_27",
            "pid_28",
            "pid_30",
            "pid_31",
            "pid_32",
            "pid_33",
            "pid_34",
            "pid_35",
            "pid_36",
            "pid_37",
            "pid_38",
            "pid_39",
        ]

        for field_path in test_cases:
            self.assertEqual(
                get_hl7_field_value(self.original_message.pid, field_path),
                get_hl7_field_value(self.new_message.pid, field_path),
            )

    def test_map_pid_29_date_of_death_transformation(self) -> None:
        result = map_pid(self.original_message, self.new_message)

        self.assertEqual(get_hl7_field_value(self.new_message.pid, "pid_29.ts_1"), "2024-12-31")
        self.assertEqual(result, ("2024-12-31", "2024-12-31"))

    def test_map_pid_29_date_of_death_resurrec(self) -> None:
        self.original_message.pid.pid_29.ts_1 = "RESURREC"
        result = map_pid(self.original_message, self.new_message)

        self.assertEqual(get_hl7_field_value(self.new_message.pid, "pid_29.ts_1"), '""')
        self.assertEqual(result, ("RESURREC", '""'))

    def test_map_pid_29_no_date_of_death(self) -> None:
        self.original_message.pid.pid_29.ts_1 = ""
        result = map_pid(self.original_message, self.new_message)

        self.assertEqual(get_hl7_field_value(self.new_message.pid, "pid_29.ts_1"), "")
        self.assertIsNone(result)

    def test_map_pid_29_empty_date_of_death(self) -> None:
        self.original_message.pid.pid_29.value = ""
        result = map_pid(self.original_message, self.new_message)

        self.assertEqual(get_hl7_field_value(self.new_message.pid, "pid_29.ts_1"), "")
        self.assertIsNone(result)

    def test_map_pid_no_pid_segment(self) -> None:
        original_message = parse_message(
            "MSH|^~\\&|PHW|PHW HL7Sender|EMPI|EMPI|2024-12-31 10:10:53||ADT^A08^ADT_A01|48209024|P|2.3.1\r"
        )
        new_message = Message(version="2.5")

        result = map_pid(original_message, new_message)

        # Should return None and not add PID segment to new message
        self.assertIsNone(result)
        self.assertFalse(hasattr(new_message, 'pid'))


if __name__ == "__main__":
    unittest.main()
