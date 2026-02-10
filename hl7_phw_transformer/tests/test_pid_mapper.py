import os
import re
import unittest

from field_utils_lib import get_hl7_field_value
from hl7apy.core import Message
from hl7apy.parser import parse_message

from hl7_phw_transformer.mappers.pid_mapper import map_pid


class TestPIDMapper(unittest.TestCase):
    def setUp(self) -> None:
        test_dir = os.path.dirname(__file__)
        hl7_path = os.path.join(test_dir, "phw-valid-message.hl7")
        with open(hl7_path, "r", encoding="utf-8") as f:
            self.base_hl7_message = f.read()
        self.original_message = parse_message(self.base_hl7_message)
        self.new_message = Message(version="2.5")

    def test_map_pid_all_direct_mappings(self) -> None:
        map_pid(self.original_message, self.new_message)

        original_pid = self.original_message.pid.to_er7()
        new_pid = self.new_message.pid.to_er7()

        # Exclude PID.29 (date of death) from this comparison as it is covered
        # explicitly in separate tests.
        def _strip_pid_29(segment_str: str) -> str:
            parts = segment_str.split("|")
            if parts and parts[0] == "PID" and len(parts) > 29:
                parts[29] = ""
            return "|".join(parts)

        self.assertEqual(_strip_pid_29(original_pid), _strip_pid_29(new_pid))

    def test_map_pid_29_date_of_death_transformation(self) -> None:
        self.original_message.pid.pid_29.ts_1 = "2024-12-31"
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
