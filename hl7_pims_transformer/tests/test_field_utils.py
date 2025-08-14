import unittest

from hl7apy.core import Message
from hl7apy.parser import parse_message

from hl7_pims_transformer.utils.field_utils import get_hl7_field_value, set_nested_field


def create_test_segments() -> tuple:
    msh_message_str = (
        "MSH|^~\\&|SENDING_APP|HOSPITAL||TEST|20250725120000||ADT^A28|123|P|2.4|||NE|NE\rEVN|A28|20250725120000\r"
    )
    msh_message = parse_message(msh_message_str)

    pid_message_str = (
        "MSH|^~\\&|TEST|TEST||TEST|20250725120000||ADT^A28|123|P|2.4|||NE|NE\r"
        "PID|1|123^^^^NH|^03^^^NI~N5022039^^^^PI||PATIENT_NAME^FIRST^^^||19900101|M|||^^^^CF11 9AD||"
        "07001231234^PRN~07001234567^ORN||ENG|M||123456789||||||||||||\r"
    )
    pid_message = parse_message(pid_message_str)

    return msh_message.msh, pid_message.pid


class TestGetHL7FieldValue(unittest.TestCase):
    def setUp(self) -> None:
        self.msh_segment, self.pid_segment = create_test_segments()

    def test_get_simple_field(self) -> None:
        result = get_hl7_field_value(self.msh_segment, "msh_3")
        self.assertEqual(result, "SENDING_APP")

    def test_get_nested_field(self) -> None:
        result = get_hl7_field_value(self.msh_segment, "msh_4.hd_1")
        self.assertEqual(result, "HOSPITAL")

    def test_get_double_nested_fields(self) -> None:
        test_cases = [
            {
                "segment": self.pid_segment,
                "field_path": "pid_5.xpn_1.fn_1",
                "expected": "PATIENT_NAME",
                "description": "deeply nested field in pid_segment",
            },
            {
                "segment": self.msh_segment,
                "field_path": "msh_7.ts_1",
                "expected": "20250725120000",
                "description": "nested timestamp field in msh_segment",
            },
        ]

        for case in test_cases:
            with self.subTest(msg=case["description"]):
                result = get_hl7_field_value(case["segment"], str(case["field_path"]))
                self.assertEqual(result, case["expected"])

    def test_get_field_with_bracket_notation(self) -> None:
        test_cases = [
            {
                "field_path": "pid_3[0].cx_1",
                "expected": "",
                "description": "first repetition of pid_3 cx_1 field - not populated",
            },
            {
                "field_path": "pid_3[0].cx_2",
                "expected": "03",
                "description": "first repetition of pid_3 cx_2 field",
            },
            {
                "field_path": "pid_3[1].cx_1",
                "expected": "N5022039",
                "description": "second repetition of pid_3 cx_1 field",
            },
            {
                "field_path": "pid_13[0].xtn_1",
                "expected": "07001231234",
                "description": "first repetition of pid_13 xtn_1 field",
            },
            {
                "field_path": "pid_13[1].xtn_1",
                "expected": "07001234567",
                "description": "second repetition of pid_13 xtn_1 field",
            },
        ]

        for case in test_cases:
            with self.subTest(msg=case["description"]):
                result = get_hl7_field_value(self.pid_segment, str(case["field_path"]))
                self.assertEqual(result, case["expected"])

    def test_get_field_with_bracket_notation_out_of_range(self) -> None:
        result = get_hl7_field_value(self.pid_segment, "pid_3[5].cx_1")
        self.assertEqual(result, "")

    def test_get_field_with_bracket_notation_missing_field(self) -> None:
        result = get_hl7_field_value(self.pid_segment, "nonexistent_field[0].value")
        self.assertEqual(result, "")

    def test_get_missing_field(self) -> None:
        result = get_hl7_field_value(self.msh_segment, "nonexistent_field")
        self.assertEqual(result, "")

    def test_get_missing_nested_field(self) -> None:
        result = get_hl7_field_value(self.msh_segment, "msh_3.nonexistent_subfield")
        self.assertEqual(result, "")

    def test_get_empty_field(self) -> None:
        result = get_hl7_field_value(self.msh_segment, "msh_5")
        self.assertEqual(result, "")

    def test_get_none_field(self) -> None:
        result = get_hl7_field_value(self.msh_segment, "msh_25")
        self.assertEqual(result, "")


class TestSetNestedField(unittest.TestCase):
    def setUp(self) -> None:
        self.msh_segment, self.pid_segment = create_test_segments()
        self.target_message = Message(version="2.5")
        self.target = self.target_message.pid

    def test_set_existing_nested_field(self) -> None:
        result = set_nested_field(self.pid_segment, self.target, "pid_5.xpn_1.fn_1")

        self.assertTrue(result)
        self.assertTrue(hasattr(self.target.pid_5.xpn_1, "fn_1"))
        copied_value = get_hl7_field_value(self.target, "pid_5.xpn_1.fn_1")
        self.assertEqual(copied_value, "PATIENT_NAME")

    def test_set_missing_field_returns_false(self) -> None:
        result = set_nested_field(self.pid_segment, self.target, "pid_5.xpn_1.missing_field")

        self.assertFalse(result)
        missing_field_value = get_hl7_field_value(self.target, "pid_5.xpn_1.missing_field")
        self.assertEqual(missing_field_value, "")

    def test_set_with_missing_intermediate_structure(self) -> None:
        set_nested_field(self.pid_segment, self.target, "pid_11.xad_1.sad_1")

        nested_field_value = get_hl7_field_value(self.target, "pid_11.xad_1.sad_1")
        self.assertEqual(nested_field_value, "")

    def test_set_field_no_subfield(self) -> None:
        msh_target = self.target_message.msh
        set_nested_field(self.msh_segment, msh_target, "msh_3")

        self.assertTrue(hasattr(msh_target, "msh_3"))
        self.assertEqual(msh_target.msh_3.value, "SENDING_APP")

    def test_set_field_with_subfield(self) -> None:
        msh_target = self.target_message.msh
        set_nested_field(self.msh_segment, msh_target, "msh_4.hd_1")

        self.assertTrue(hasattr(msh_target.msh_4, "hd_1"))
        self.assertEqual(msh_target.msh_4.hd_1.value, "HOSPITAL")

    def test_set_nonexistent_field(self) -> None:
        msh_target = self.target_message.msh
        initial_msh3_exists = hasattr(msh_target, "msh_3")

        set_nested_field(self.msh_segment, msh_target, "missing_field")

        final_msh3_exists = hasattr(msh_target, "msh_3")
        self.assertEqual(initial_msh3_exists, final_msh3_exists)

    def test_set_empty_field_copied_over(self) -> None:
        msh_target = self.target_message.msh
        set_nested_field(self.msh_segment, msh_target, "msh_5")

        self.assertTrue(hasattr(msh_target, "msh_5"))
        self.assertEqual(str(msh_target.msh_5.value), "")

    def test_set_nonexistent_subfield(self) -> None:
        msh_target = self.target_message.msh
        set_nested_field(self.msh_segment, msh_target, "msh_3.nonexistent_subfield")

        self.assertTrue(hasattr(msh_target, "msh_3"))
