from __future__ import annotations

import unittest

from pydantic import ValidationError

from lookup_service.errors import InvalidKeyError
from lookup_service.keys import canonical_key, normalise_part
from lookup_service.models import KeyPartRule, TableDefinition


def ward_definition() -> TableDefinition:
    return TableDefinition(
        name="ward_map",
        key_columns=("sending_facility", "ward_code"),
        value_columns=("national_ward_code",),
        default_value_column="national_ward_code",
        key_normalisation={"ward_code": KeyPartRule(case="upper")},
    )


class NormalisePartTests(unittest.TestCase):
    def test_default_rule_trims_and_preserves_case(self) -> None:
        self.assertEqual(normalise_part("  Ab ", KeyPartRule()), "Ab")

    def test_upper_and_lower(self) -> None:
        self.assertEqual(normalise_part(" ab ", KeyPartRule(case="upper")), "AB")
        self.assertEqual(normalise_part(" AB ", KeyPartRule(case="lower")), "ab")

    def test_trim_disabled_keeps_whitespace(self) -> None:
        self.assertEqual(normalise_part(" a ", KeyPartRule(trim=False)), " a ")


class CanonicalKeyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.definition = ward_definition()

    def test_positional_composite_key(self) -> None:
        self.assertEqual(canonical_key(self.definition, ["FAC1", " w2 "]), ("FAC1", "W2"))

    def test_named_key_is_reordered_to_key_columns(self) -> None:
        key = canonical_key(self.definition, named={"ward_code": "w2", "sending_facility": "FAC1"})
        self.assertEqual(key, ("FAC1", "W2"))

    def test_named_and_positional_give_same_key(self) -> None:
        self.assertEqual(
            canonical_key(self.definition, ["FAC1", "W2"]),
            canonical_key(self.definition, named={"sending_facility": "FAC1", "ward_code": "W2"}),
        )

    def test_rejects_wrong_arity(self) -> None:
        with self.assertRaisesRegex(InvalidKeyError, "Expected 2 key part"):
            canonical_key(self.definition, ["FAC1"])

    def test_rejects_mixed_styles(self) -> None:
        with self.assertRaisesRegex(InvalidKeyError, "not both"):
            canonical_key(self.definition, ["FAC1", "W2"], {"ward_code": "W2"})

    def test_rejects_missing_key(self) -> None:
        with self.assertRaisesRegex(InvalidKeyError, "No key supplied"):
            canonical_key(self.definition)

    def test_rejects_unknown_part_name(self) -> None:
        with self.assertRaisesRegex(InvalidKeyError, "Unknown key part"):
            canonical_key(self.definition, named={"sending_facility": "FAC1", "ward_code": "W2", "bed": "1"})

    def test_rejects_missing_part_name(self) -> None:
        with self.assertRaisesRegex(InvalidKeyError, "Missing key part"):
            canonical_key(self.definition, named={"sending_facility": "FAC1"})

    def test_rejects_part_empty_after_normalisation(self) -> None:
        with self.assertRaisesRegex(InvalidKeyError, "'ward_code' is empty"):
            canonical_key(self.definition, ["FAC1", "   "])

    def test_error_carries_table_name(self) -> None:
        with self.assertRaises(InvalidKeyError) as ctx:
            canonical_key(self.definition, ["FAC1"])
        self.assertEqual(ctx.exception.table, "ward_map")


class TableDefinitionTests(unittest.TestCase):
    def test_default_value_column_must_be_a_value_column(self) -> None:
        with self.assertRaises(ValidationError):
            TableDefinition(name="t", key_columns=("a",), value_columns=("b",), default_value_column="a")

    def test_columns_must_be_unique(self) -> None:
        with self.assertRaises(ValidationError):
            TableDefinition(name="t", key_columns=("a",), value_columns=("a",), default_value_column="a")

    def test_rejects_unsafe_column_name(self) -> None:
        with self.assertRaises(ValidationError):
            TableDefinition(name="t", key_columns=("a b",), value_columns=("c",), default_value_column="c")

    def test_rejects_invalid_table_name(self) -> None:
        with self.assertRaises(ValidationError):
            TableDefinition(name="Bad Name", key_columns=("a",), value_columns=("b",), default_value_column="b")

    def test_normalisation_must_reference_key_columns(self) -> None:
        with self.assertRaises(ValidationError):
            TableDefinition(
                name="t",
                key_columns=("a",),
                value_columns=("b",),
                default_value_column="b",
                key_normalisation={"b": KeyPartRule(case="upper")},
            )


if __name__ == "__main__":
    unittest.main()
