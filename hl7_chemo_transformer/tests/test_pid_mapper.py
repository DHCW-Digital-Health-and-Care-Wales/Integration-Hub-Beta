import unittest

from hl7apy.core import Message
from hl7apy.parser import parse_message

from hl7_chemo_transformer.mappers.pid_mapper import map_pid
from hl7_chemo_transformer.utils.field_utils import get_hl7_field_value


class TestPIDMapper(unittest.TestCase):
    def setUp(self) -> None:
        self.base_hl7_message = (
            "MSH|^~\\&|224|224|100|100|20250624162400||ADT^A31|109088442894725|P|2.4|||NE|NE\r"
            "PID|1|1000000001^^^^NH|1000000001^^^^NH~V100000A^^^^PAS||TEST^TEST^^^Ms.||20000101000000|F|||1 TEST^TEST^TEST^TEST^CF11 9AD||07000000001^PRN^^test@test.co.uk~07000000001^PRS~07000000001^PRN^^test@test.co.uk~|07000000001^WPN||||||||A||||||||||1\r"
        )
        self.original_message = parse_message(self.base_hl7_message)
        self.new_message = Message(version="2.5")

    def test_map_pid_all_direct_mappings(self) -> None:
        map_pid(self.original_message, self.new_message)

        test_cases = [
            "pid_1",
            "pid_5.xpn_1.fn_1",
            "pid_5.xpn_2",
            "pid_5.xpn_3",
            "pid_5.xpn_4",
            "pid_5.xpn_5",
            "pid_5.xpn_6",
            "pid_5.xpn_7",
            "pid_5.xpn_8",
            "pid_5.xpn_9.ce_1",
            "pid_5.xpn_10.dr_1.ts_1",
            "pid_5.xpn_10.dr_2.ts_1",
            "pid_5.xpn_11",
            "pid_6.xpn_1.fn_1",
            "pid_7.ts_1",
            "pid_8",
            "pid_9.xpn_1.fn_1",
            "pid_10.ce_1",
            "pid_11.xad_1.sad_1",
            "pid_11.xad_2",
            "pid_11.xad_3",
            "pid_11.xad_4",
            "pid_11.xad_5",
            "pid_11.xad_7",
            "pid_11.xad_8",
            "pid_13.xtn_1",
            "pid_13.xtn_2",
            "pid_14.xtn_1",
            "pid_14.xtn_2",
            "pid_17.ce_1",
            "pid_22.ce_1",
            "pid_29.ts_1",
        ]

        for field_path in test_cases:
            with self.subTest(field=field_path):
                self.assertEqual(
                    get_hl7_field_value(self.original_message.pid, field_path),
                    get_hl7_field_value(self.new_message.pid, field_path),
                )

    def test_map_pid_patient_id_logic(self) -> None:
        map_pid(self.original_message, self.new_message)

        self.assertEqual("NHS", get_hl7_field_value(self.new_message.pid.pid_3[0], "cx_4.hd_1"))
        self.assertEqual("NH", get_hl7_field_value(self.new_message.pid.pid_3[0], "cx_5"))
        self.assertEqual("PI", get_hl7_field_value(self.new_message.pid.pid_3[1], "cx_5"))

    def test_map_pid_health_board_logic(self) -> None:
        map_pid(self.original_message, self.new_message)

        original_pid2 = get_hl7_field_value(self.original_message.pid, "pid_2.cx_1")
        new_pid3_rep2 = get_hl7_field_value(self.new_message.pid.pid_3[1], "cx_1")

        self.assertEqual(f"VCC{original_pid2}", new_pid3_rep2)

    def test_map_pid_32_to_31_mapping(self) -> None:
        map_pid(self.original_message, self.new_message)

        self.assertEqual(
            get_hl7_field_value(self.original_message.pid, "pid_32"),
            get_hl7_field_value(self.new_message.pid, "pid_31"),
        )


if __name__ == "__main__":
    unittest.main()
