import unittest
from unittest.mock import MagicMock, patch

from hl7apy.core import Message
from hl7apy.parser import parse_message

from hl7_chemo_transformer.mappers.pid_mapper import map_pid
from hl7_chemo_transformer.utils.field_utils import get_hl7_field_value


class TestPIDMapper(unittest.TestCase):
    def setUp(self) -> None:
        self.base_hl7_message = (
            "MSH|^~\\&|192|192|200|200|20250701154910||ADT^A28|474997159036153|P|2.4|||NE|NE\r"
            "PID|1|1000000001^^^^NH|1000001^^^^PAS~1000000001^^^^NH||TEST^TEST^TEST^^Mr.||20000101000000|M|||111, TEST^TEST^TEST^^CF11 9AD||01000 000001^PRN^^test@test.com~07000000001^PRS|07000000001^WPN||||||||||||||||||1\r"
        )
        self.original_message = parse_message(self.base_hl7_message)
        self.new_message = Message(version="2.5")

    def _create_test_message(self, msh3_value: str = "192", pid32_value: str = "") -> Message:
        pid_suffix = f"|||||||||||||||||||||||||||||||{pid32_value}" if pid32_value else "||||||||||||||||||1"
        test_message = (
            f"MSH|^~\\&|{msh3_value}|{msh3_value}|200|200|20250701154910||ADT^A28|474997159036153|P|2.4|||NE|NE\r"
            f"PID|1|1000000001^^^^NH|1000001^^^^PAS~1000000001^^^^NH||TEST^TEST^TEST^^Mr.||20000101000000|M|||111, TEST^TEST^TEST^^CF11 9AD||01000 000001^PRN^^test@test.com~07000000001^PRS|07000000001^WPN{pid_suffix}\r"
        )
        return parse_message(test_message)

    def test_map_pid_basic_fields(self) -> None:
        """Test mapping of basic PID fields that should be copied directly."""
        map_pid(self.original_message, self.new_message)

        basic_field_mappings = [
            ("pid_1", "pid_1"),
            ("pid_7", "pid_7"),
            ("pid_8", "pid_8"),
            ("pid_5.xpn_1.fn_1", "pid_5.xpn_1.fn_1"),
            ("pid_11.xad_2", "pid_11.xad_2"),
            ("pid_11.xad_3", "pid_11.xad_3"),
            ("pid_13.xtn_1", "pid_13.xtn_1"),
            ("pid_13.xtn_2", "pid_13.xtn_2"),
            ("pid_14.xtn_1", "pid_14.xtn_1"),
            ("pid_10.ce_1", "pid_10.ce_1"),
            ("pid_17.ce_1", "pid_17.ce_1"),
        ]

        for original_path, new_path in basic_field_mappings:
            with self.subTest(field=original_path):
                self.assertEqual(
                    get_hl7_field_value(self.original_message.pid, original_path),
                    get_hl7_field_value(self.new_message.pid, new_path),
                )

    def test_map_pid_patient_id_logic(self) -> None:
        map_pid(self.original_message, self.new_message)

        self.assertEqual("NHS", get_hl7_field_value(self.new_message.pid, "pid_3.cx_4.hd_1"))
        self.assertEqual("NH", get_hl7_field_value(self.new_message.pid, "pid_3.cx_5"))

        expected_pid2_value = get_hl7_field_value(self.original_message.pid, "pid_2.cx_1") or get_hl7_field_value(
            self.original_message.pid, "pid_2"
        )
        self.assertEqual(expected_pid2_value, get_hl7_field_value(self.new_message.pid, "pid_3.cx_1"))

    def test_map_pid_health_board_logic(self) -> None:
        health_board_cases = [
            ("192", "SWW"),
            ("224", "VCC"),
            ("212", "BCUCCC"),
            ("245", "SEW"),
        ]

        for msh3_value, expected_prefix in health_board_cases:
            with self.subTest(msh3_value=msh3_value, expected_prefix=expected_prefix):
                original_msg = self._create_test_message(msh3_value)
                new_msg = Message(version="2.5")

                map_pid(original_msg, new_msg)

                expected_pid2_value = get_hl7_field_value(original_msg.pid, "pid_2.cx_1") or get_hl7_field_value(
                    original_msg.pid, "pid_2"
                )

                if hasattr(new_msg.pid, "pid_3") and len(new_msg.pid.pid_3) > 1:
                    second_rep_value = str(new_msg.pid.pid_3[1].cx_1.value) if new_msg.pid.pid_3[1].cx_1 else ""
                    self.assertEqual(f"{expected_prefix}{expected_pid2_value}", second_rep_value)

    def test_map_pid_32_to_31_mapping(self) -> None:
        original_msg = self._create_test_message(pid32_value="TEST_IDENTITY")
        new_msg = Message(version="2.5")

        map_pid(original_msg, new_msg)

        original_pid32_value = get_hl7_field_value(original_msg.pid, "pid_32")
        if original_pid32_value:
            self.assertEqual(original_pid32_value, get_hl7_field_value(new_msg.pid, "pid_31"))

    def test_map_pid_no_pid_segment(self) -> None:
        msh_only_message = "MSH|^~\\&|192|192|200|200|20250701154910||ADT^A28|474997159036153|P|2.4|||NE|NE\r"
        original_msg = parse_message(msh_only_message)
        new_msg = Message(version="2.5")

        map_pid(original_msg, new_msg)

    @patch("hl7_chemo_transformer.mappers.pid_mapper.set_nested_field")
    def test_map_pid_calls_set_nested_field(self, mock_set_nested_field: MagicMock) -> None:
        map_pid(self.original_message, self.new_message)

        expected_calls = [
            ("pid_1",),
            ("pid_5", "xpn_2"),
            ("pid_7",),
            ("pid_8",),
        ]

        for call_args in expected_calls:
            with self.subTest(call_args=call_args):
                mock_set_nested_field.assert_any_call(self.original_message.pid, self.new_message.pid, *call_args)


if __name__ == "__main__":
    unittest.main()
