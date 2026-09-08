"""Tests for pid_reference_mapper — field mapping, empty-value rules, and in-place mutation."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from field_utils_lib import get_hl7_field_value
from hl7apy.parser import parse_message

from hl7_core_reference_transformer.mappers.pid_reference_mapper import (
    FIELD_TYPE_MAP,
    _is_empty_or_hl7_null,
    _set_field_value,
    apply_core_reference_mapping,
)
from tests.messages import A28_ALL_FIELDS_POPULATED, A31_ALL_FIELDS_EMPTY, A40_SEX_HL7_NULL, MSH_ONLY_NO_PID

_LOOKUP_TABLE_NAME = "FioranoCodeTranslation"


def _rows_for_all_fields() -> list[dict[str, str]]:
    return [
        {"FromCode": "1", "Type": "Sex", "ToCode": "M"},
        {"FromCode": "Mr.", "Type": "Title", "ToCode": "Mr"},
        {"FromCode": "EN", "Type": "Language", "ToCode": "eng"},
        {"FromCode": "11", "Type": "Marital Status", "ToCode": "S"},
        {"FromCode": "22", "Type": "Religion", "ToCode": "REL22"},
        {"FromCode": "33", "Type": "Ethnicity", "ToCode": "ETH33"},
    ]


class TestApplyCoreReferenceMapping(unittest.TestCase):
    def test_all_six_fields_translated(self) -> None:
        message = parse_message(A28_ALL_FIELDS_POPULATED)
        wrds_service = MagicMock()
        wrds_service.get_result_set.return_value = _rows_for_all_fields()
        wrds_service.get_to_code.side_effect = lambda rows, from_code, reference_type: next(
            (row["ToCode"] for row in rows if row["FromCode"] == from_code and row["Type"] == reference_type),
            "",
        )

        result = apply_core_reference_mapping(message, wrds_service, _LOOKUP_TABLE_NAME)

        self.assertIs(result, message)  # same object, mutated in place
        self.assertEqual(get_hl7_field_value(result.pid, "pid_8"), "M")
        self.assertEqual(get_hl7_field_value(result.pid, "pid_5.xpn_5"), "Mr")
        self.assertEqual(get_hl7_field_value(result.pid, "pid_15.ce_1"), "eng")
        self.assertEqual(get_hl7_field_value(result.pid, "pid_16.ce_1"), "S")
        self.assertEqual(get_hl7_field_value(result.pid, "pid_17.ce_1"), "REL22")
        self.assertEqual(get_hl7_field_value(result.pid, "pid_22.ce_1"), "ETH33")

    def test_calls_get_result_set_once_with_from_and_to_system(self) -> None:
        message = parse_message(A28_ALL_FIELDS_POPULATED)
        wrds_service = MagicMock()
        wrds_service.get_result_set.return_value = []
        wrds_service.get_to_code.return_value = ""

        apply_core_reference_mapping(message, wrds_service, _LOOKUP_TABLE_NAME)

        wrds_service.get_result_set.assert_called_once_with(
            lookup_table_name=_LOOKUP_TABLE_NAME,
            attributes=[("FromSystem", "349"), ("ToSystem", "100")],
            attributes_to_retrieve=["FromCode", "type", "ToCode"],
            exact_match=True,
        )

    def test_unrelated_fields_untouched(self) -> None:
        message = parse_message(A28_ALL_FIELDS_POPULATED)
        wrds_service = MagicMock()
        wrds_service.get_result_set.return_value = _rows_for_all_fields()
        wrds_service.get_to_code.return_value = "M"

        apply_core_reference_mapping(message, wrds_service, _LOOKUP_TABLE_NAME)

        # PID-5 family/given name components must be untouched — only xpn_5 (Title) changes.
        self.assertEqual(get_hl7_field_value(message.pid, "pid_5.xpn_1.fn_1"), "TEST")
        self.assertEqual(get_hl7_field_value(message.pid, "pid_5.xpn_2"), "TEST")
        # PID-3 (patient identifier) is not one of the six in-scope fields.
        self.assertEqual(get_hl7_field_value(message.pid, "pid_3"), "1000000001^^^^NH")

    def test_all_fields_empty_skips_wrds_call_entirely(self) -> None:
        message = parse_message(A31_ALL_FIELDS_EMPTY)
        wrds_service = MagicMock()

        result = apply_core_reference_mapping(message, wrds_service, _LOOKUP_TABLE_NAME)

        wrds_service.get_result_set.assert_not_called()
        wrds_service.get_to_code.assert_not_called()
        self.assertIs(result, message)

    def test_hl7_null_sex_left_untouched(self) -> None:
        message = parse_message(A40_SEX_HL7_NULL)
        wrds_service = MagicMock()

        apply_core_reference_mapping(message, wrds_service, _LOOKUP_TABLE_NAME)

        wrds_service.get_result_set.assert_not_called()
        self.assertEqual(get_hl7_field_value(message.pid, "pid_8"), '""')

    def test_no_matching_row_clears_field_to_empty(self) -> None:
        message = parse_message(A28_ALL_FIELDS_POPULATED)
        wrds_service = MagicMock()
        wrds_service.get_result_set.return_value = []  # no rows returned at all
        wrds_service.get_to_code.return_value = ""

        apply_core_reference_mapping(message, wrds_service, _LOOKUP_TABLE_NAME)

        self.assertEqual(get_hl7_field_value(message.pid, "pid_8"), "")

    def test_missing_pid_segment_returns_message_unchanged(self) -> None:
        message = parse_message(MSH_ONLY_NO_PID)
        wrds_service = MagicMock()

        result = apply_core_reference_mapping(message, wrds_service, _LOOKUP_TABLE_NAME)

        wrds_service.get_result_set.assert_not_called()
        self.assertIs(result, message)


class TestIsEmptyOrHl7Null(unittest.TestCase):
    def test_empty_string_is_empty(self) -> None:
        self.assertTrue(_is_empty_or_hl7_null(""))

    def test_hl7_null_value_is_empty(self) -> None:
        self.assertTrue(_is_empty_or_hl7_null('""'))

    def test_populated_value_is_not_empty(self) -> None:
        self.assertFalse(_is_empty_or_hl7_null("M"))


class TestFieldTypeMap(unittest.TestCase):
    def test_contains_all_six_confirmed_categories(self) -> None:
        self.assertEqual(
            set(FIELD_TYPE_MAP.values()),
            {"Sex", "Title", "Language", "Marital Status", "Religion", "Ethnicity"},
        )


class TestSetFieldValue(unittest.TestCase):
    def test_sets_simple_field(self) -> None:
        message = parse_message(A28_ALL_FIELDS_POPULATED)

        _set_field_value(message.pid, "pid_8", "F")

        self.assertEqual(get_hl7_field_value(message.pid, "pid_8"), "F")

    def test_sets_nested_component_only(self) -> None:
        message = parse_message(A28_ALL_FIELDS_POPULATED)

        _set_field_value(message.pid, "pid_16.ce_1", "S")

        self.assertEqual(get_hl7_field_value(message.pid, "pid_16.ce_1"), "S")


if __name__ == "__main__":
    unittest.main()
