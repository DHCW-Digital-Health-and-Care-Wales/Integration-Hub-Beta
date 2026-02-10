import unittest

from field_utils_lib import get_hl7_field_value
from hl7apy.core import Message
from hl7apy.parser import parse_message

from hl7_phw_transformer.mappers.pid_mapper import map_pid


class TestPIDMapper(unittest.TestCase):
    def setUp(self) -> None:
        self.base_hl7_message = (
            "MSH|^~\\&|252|252|100|100|2025-05-05 23:23:32||ADT^A31^ADT_A05|"
            "202505052323364444444444|P|2.5|||||GBR||EN\r"
            "EVN||20250502092900|20250505232332|||20250505232332\r"
            "PID|||8888888^^^252^PI~4444444444^^^NHS^NH||MYSURNAME^MYFNAME^MYMNAME^^MR||"
            "19990101|M|^^||99, MY ROAD^MY PLACE^MY CITY^MY COUNTY^SA99 1XX^^H"
            "~SECOND1^SECOND2^SECOND3^SECOND4^SB99 9SB^^H||"
            "^^^~||||||||||||||||2024-12-31|||01\r"
            "PD1|||^^W00000^|G999999\r"
            "PV1||U\r"
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

    def test_map_pid_3_preserves_all_repetitions(self) -> None:
        map_pid(self.original_message, self.new_message)
        self.assertEqual(len(self.original_message.pid.pid_3), len(self.new_message.pid.pid_3))
        for i in range(len(self.original_message.pid.pid_3)):
            self.assertEqual(
                self.original_message.pid.pid_3[i].value,
                self.new_message.pid.pid_3[i].value,
                f"PID.3 repetition {i} mismatch",
            )

    def test_map_pid_11_preserves_all_repetitions(self) -> None:
        map_pid(self.original_message, self.new_message)
        self.assertEqual(len(self.original_message.pid.pid_11), len(self.new_message.pid.pid_11))
        for i in range(len(self.original_message.pid.pid_11)):
            self.assertEqual(
                self.original_message.pid.pid_11[i].value,
                self.new_message.pid.pid_11[i].value,
                f"PID.11 repetition {i} mismatch",
            )

    def test_map_pid_no_pid_segment(self) -> None:
        original_message = parse_message(
            "MSH|^~\\&|252|252|100|100|2025-05-05 23:23:32||ADT^A31^ADT_A05|"
            "202505052323364444444444|P|2.5|||||GBR||EN\r"
        )
        new_message = Message(version="2.5")

        result = map_pid(original_message, new_message)

        self.assertIsNone(result)
        segments = [s.name for s in new_message.children]
        self.assertEqual(segments, ["MSH"])


if __name__ == "__main__":
    unittest.main()
