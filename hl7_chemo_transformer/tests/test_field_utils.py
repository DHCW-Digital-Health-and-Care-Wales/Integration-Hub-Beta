import unittest

from hl7apy.core import Message
from hl7apy.parser import parse_message

from hl7_chemo_transformer.utils.field_utils import get_hl7_field_value, safe_copy_nested_field, set_nested_field


def create_test_segments() -> tuple:
    msh_message_str = (
        "MSH|^~\\&|SENDING_APP|HOSPITAL||TEST|20250725120000||ADT^A28|123|P|2.4|||NE|NE\rEVN|A28|20250725120000\r"
    )
    msh_message = parse_message(msh_message_str)

    pid_message_str = (
        "MSH|^~\\&|TEST|TEST||TEST|20250725120000||ADT^A28|123|P|2.4|||NE|NE\r"
        "PID|1|123^^^^NH|123^^^^NH||PATIENT_NAME^FIRST^^^||19900101|M|||123 MAIN ST^^CITY^STATE^12345||555-1234^PRN||ENG|M||123456789||||||||||||\r"
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
        self.msh_segment, _ = create_test_segments()
        self.source = self.msh_segment

        target_message = Message(version="2.5")
        self.target = target_message.msh

    def test_set_field_no_subfield(self) -> None:
        set_nested_field(self.source, self.target, "msh_3")

        self.assertTrue(hasattr(self.target, "msh_3"))
        self.assertEqual(self.target.msh_3.value, "SENDING_APP")

    def test_set_field_with_subfield(self) -> None:
        set_nested_field(self.source, self.target, "msh_4", "hd_1")

        self.assertTrue(hasattr(self.target.msh_4, "hd_1"))
        self.assertEqual(self.target.msh_4.hd_1.value, "HOSPITAL")

    def test_set_nonexistent_field(self) -> None:
        initial_msh3_exists = hasattr(self.target, "msh_3")

        set_nested_field(self.source, self.target, "missing_field")

        final_msh3_exists = hasattr(self.target, "msh_3")
        self.assertEqual(initial_msh3_exists, final_msh3_exists)

    def test_set_empty_field_copied_over(self) -> None:
        set_nested_field(self.source, self.target, "msh_5")

        self.assertTrue(hasattr(self.target, "msh_5"))
        self.assertEqual(str(self.target.msh_5.value), "")

    def test_set_nonexistent_subfield(self) -> None:
        set_nested_field(self.source, self.target, "msh_3", "nonexistent_subfield")

        self.assertTrue(hasattr(self.target, "msh_3"))


class TestSafeCopyNestedField(unittest.TestCase):
    def setUp(self) -> None:
        self.msh_segment, self.pid_segment = create_test_segments()

    def test_safe_copy_existing_nested_field(self) -> None:
        target_message = Message(version="2.5")
        target = target_message.pid

        result = safe_copy_nested_field(self.pid_segment, target, "pid_5.xpn_1.fn_1")

        self.assertTrue(result)
        self.assertTrue(hasattr(target.pid_5.xpn_1, "fn_1"))
        copied_value = get_hl7_field_value(target, "pid_5.xpn_1.fn_1")
        self.assertEqual(copied_value, "PATIENT_NAME")

    def test_safe_copy_missing_field_returns_false(self) -> None:
        target_message = Message(version="2.5")
        target = target_message.pid

        result = safe_copy_nested_field(self.pid_segment, target, "pid_5.xpn_1.missing_field")

        self.assertFalse(result)
        missing_field_value = get_hl7_field_value(target, "pid_5.xpn_1.missing_field")
        self.assertEqual(missing_field_value, "")

    def test_safe_copy_with_missing_intermediate_structure(self) -> None:
        target_message = Message(version="2.5")
        target = target_message.pid

        result = safe_copy_nested_field(self.pid_segment, target, "pid_5.xpn_1.fn_1")

        if result:
            self.assertTrue(hasattr(target.pid_5.xpn_1, "fn_1"))
            copied_value = get_hl7_field_value(target, "pid_5.xpn_1.fn_1")
            self.assertEqual(copied_value, "PATIENT_NAME")
        else:
            nested_field_value = get_hl7_field_value(target, "pid_5.xpn_1.fn_1")
            self.assertEqual(nested_field_value, "")
