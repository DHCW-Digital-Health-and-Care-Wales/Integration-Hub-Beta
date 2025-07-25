import unittest
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from hl7_chemo_transformer.utils.field_utils import get_hl7_field_value, set_nested_field


@dataclass
class _MockHL7Value:
    """
    Internal mock for HL7 value objects
    """

    value: Optional[Any] = None


@dataclass
class _MockHL7Field:
    """
    Internal mock for HL7 field objects, aims to mirror HL7 segment fields with optional subfields
    """

    value: Optional[Any] = None
    subfields: Dict[str, Any] = field(default_factory=dict)

    def __getattr__(self, name: str) -> Any:
        # similar to hl7apy
        if name in self.subfields:
            return self.subfields[name]
        raise AttributeError(f"'{self.__class__.__name__}' has no attribute '{name}'")


def create_test_segments() -> tuple[_MockHL7Field, _MockHL7Field]:
    # Create a mock MSH segment with various field types
    msh_segment = _MockHL7Field(
        value="MSH_SEGMENT",
        subfields={
            "msh_3": _MockHL7Field("SENDING_APP"),
            "msh_4": _MockHL7Field(value="MSH_4", subfields={"hd_1": _MockHL7Field("HOSPITAL")}),
            "msh_7": _MockHL7Field(value="20250725120000", subfields={"ts_1": _MockHL7Field("20250725")}),
            "empty_field": _MockHL7Field(""),
            "none_field": _MockHL7Field(None),
        },
    )

    # Add double-nested value
    nested_value = _MockHL7Value("NESTED_VALUE")
    msh_segment.subfields["double_nested"] = _MockHL7Field(nested_value)

    # Create a mock PID segment
    pid_segment = _MockHL7Field(
        value="PID_SEGMENT",
        subfields={
            "pid_5": _MockHL7Field(
                value="PID_5",
                subfields={"xpn_1": _MockHL7Field(value="XPN_1", subfields={"fn_1": _MockHL7Field("PATIENT_NAME")})},
            )
        },
    )

    return msh_segment, pid_segment


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
                "field_path": "double_nested",
                "expected": "NESTED_VALUE",
                "description": "double-nested value in msh_segment",
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
        result = get_hl7_field_value(self.msh_segment, "empty_field")
        self.assertEqual(result, "")

    def test_get_none_field(self) -> None:
        result = get_hl7_field_value(self.msh_segment, "none_field")
        self.assertEqual(result, "")


class TestSetNestedField(unittest.TestCase):
    def setUp(self) -> None:
        self.msh_segment, _ = create_test_segments()
        self.source = self.msh_segment
        self.target = _MockHL7Field(value="TARGET", subfields={"msh_7": _MockHL7Field(value="TARGET_MSH_7")})

    def test_set_field_no_subfield(self) -> None:
        set_nested_field(self.source, self.target, "msh_3")

        self.assertTrue(hasattr(self.target, "msh_3"))
        self.assertEqual(self.target.msh_3.value, "SENDING_APP")

    def test_set_field_with_subfield(self) -> None:
        # Create target with msh_4 field but no hd_1 subfield
        target = _MockHL7Field(subfields={"msh_4": _MockHL7Field(value="TARGET_MSH_4")})

        set_nested_field(self.source, target, "msh_4", "hd_1")

        self.assertTrue(hasattr(target.msh_4, "hd_1"))
        self.assertEqual(target.msh_4.hd_1.value, "HOSPITAL")

    def test_set_nonexistent_field(self) -> None:
        target = _MockHL7Field()

        set_nested_field(self.source, target, "missing_field")

        self.assertFalse(hasattr(target, "missing_field"))

    def test_set_empty_field_copied_over(self) -> None:
        target = _MockHL7Field()

        set_nested_field(self.source, target, "empty_field")

        self.assertTrue(hasattr(target, "empty_field"))
        self.assertEqual(target.empty_field.value, "")

    def test_set_none_field_copied_over(self) -> None:
        target = _MockHL7Field()

        set_nested_field(self.source, target, "none_field")

        self.assertTrue(hasattr(target, "none_field"))
        self.assertEqual(target.none_field.value, None)

    def test_set_nonexistent_subfield(self) -> None:
        target = _MockHL7Field(subfields={"msh_3": _MockHL7Field(value="target_msh_3")})

        set_nested_field(self.source, target, "msh_3", "nonexistent_subfield")

        self.assertTrue(hasattr(target, "msh_3"))
        self.assertFalse(hasattr(target.msh_3, "nonexistent_subfield"))
