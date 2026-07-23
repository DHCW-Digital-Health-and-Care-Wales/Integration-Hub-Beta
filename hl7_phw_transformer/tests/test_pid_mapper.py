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

        original_pid = self.original_message.pid.to_er7()
        new_pid = self.new_message.pid.to_er7()

        # Exclude PID.3 and PID.29 from this comparison as these are conditionally
        # transformed and covered by dedicated tests.
        def _strip_pid_3_and_29(segment_str: str) -> str:
            parts = segment_str.split("|")
            if parts and parts[0] == "PID" and len(parts) > 29:
                parts[3] = ""
                parts[29] = ""
            return "|".join(parts)

        self.assertEqual(_strip_pid_3_and_29(original_pid), _strip_pid_3_and_29(new_pid))

    def test_map_pid_29_date_of_death_timezone_removed(self) -> None:
        self.original_message.pid.pid_29.ts_1 = "20241231101053+0000"
        result = map_pid(self.original_message, self.new_message)

        self.assertEqual(get_hl7_field_value(self.new_message.pid, "pid_29.ts_1"), "20241231101053")
        self.assertEqual(result, ("20241231101053+0000", "20241231101053"))

    def test_map_pid_29_date_of_death_short_value_is_blank(self) -> None:
        self.original_message.pid.pid_29.ts_1 = "202401"
        result = map_pid(self.original_message, self.new_message)

        self.assertEqual(get_hl7_field_value(self.new_message.pid, "pid_29.ts_1"), '""')
        self.assertEqual(result, ("202401", '""'))

    def test_map_pid_29_no_date_of_death(self) -> None:
        self.original_message.pid.pid_29.ts_1 = ""
        result = map_pid(self.original_message, self.new_message)

        self.assertEqual(get_hl7_field_value(self.new_message.pid, "pid_29.ts_1"), '""')
        self.assertIsNone(result)

    def test_map_pid_29_empty_date_of_death(self) -> None:
        self.original_message.pid.pid_29.value = ""
        result = map_pid(self.original_message, self.new_message)

        self.assertEqual(get_hl7_field_value(self.new_message.pid, "pid_29.ts_1"), '""')
        self.assertIsNone(result)

    def test_map_pid_3_maps_rep1_for_ni(self) -> None:
        self.original_message.pid.pid_3[0].cx_1 = "4444444444"
        self.original_message.pid.pid_3[0].cx_5 = "NI"

        map_pid(self.original_message, self.new_message)

        self.assertEqual(get_hl7_field_value(self.new_message.pid, "pid_3[0].cx_1"), "4444444444")
        self.assertEqual(get_hl7_field_value(self.new_message.pid, "pid_3[0].cx_4.hd_1"), "NHS")
        self.assertEqual(get_hl7_field_value(self.new_message.pid, "pid_3[0].cx_5"), "NH")

    def test_map_pid_3_rep1_blank_when_not_ni(self) -> None:
        self.original_message.pid.pid_3[0].cx_1 = "4444444444"
        self.original_message.pid.pid_3[0].cx_5 = "PI"

        map_pid(self.original_message, self.new_message)

        self.assertEqual(get_hl7_field_value(self.new_message.pid, "pid_3[0].cx_1"), "")
        self.assertEqual(get_hl7_field_value(self.new_message.pid, "pid_3[0].cx_4.hd_1"), "")
        self.assertEqual(get_hl7_field_value(self.new_message.pid, "pid_3[0].cx_5"), "")

    def test_map_pid_3_maps_rep2_for_pi(self) -> None:
        self.original_message.pid.pid_3[1].cx_1 = "8888888"
        self.original_message.pid.pid_3[1].cx_5 = "PI"

        map_pid(self.original_message, self.new_message)

        self.assertEqual(get_hl7_field_value(self.new_message.pid, "pid_3[1].cx_1"), "8888888")
        self.assertEqual(get_hl7_field_value(self.new_message.pid, "pid_3[1].cx_4.hd_1"), "103")
        self.assertEqual(get_hl7_field_value(self.new_message.pid, "pid_3[1].cx_5"), "PI")

    def test_map_pid_3_rep2_blank_when_not_pi(self) -> None:
        self.original_message.pid.pid_3[1].cx_1 = "8888888"
        self.original_message.pid.pid_3[1].cx_5 = "NI"

        map_pid(self.original_message, self.new_message)

        self.assertEqual(get_hl7_field_value(self.new_message.pid, "pid_3[1].cx_1"), "")
        self.assertEqual(get_hl7_field_value(self.new_message.pid, "pid_3[1].cx_4.hd_1"), "")
        self.assertEqual(get_hl7_field_value(self.new_message.pid, "pid_3[1].cx_5"), "")

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
