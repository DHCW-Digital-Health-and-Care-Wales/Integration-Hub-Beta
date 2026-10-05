from __future__ import annotations

import unittest

from pydantic import ValidationError

from lookup_service.csv_import import build_definition, decode_csv_bytes, import_rows, read_csv
from lookup_service.errors import InvalidUploadError
from lookup_service.mapping.model import FieldSpec, RecordMapping
from lookup_service.mapping.transforms import apply_transforms
from lookup_service.models import KeyPartRule, TableDefinition
from tests.helpers import codes_definition


class ReadCsvTests(unittest.TestCase):
    def test_skips_blank_lines_and_tracks_physical_line_numbers(self) -> None:
        document, errors = read_csv('code,label\n\nA,"multi\nline"\nB,Beta\n')
        self.assertEqual(errors, [])
        self.assertEqual(document.header, ["code", "label"])
        # The quoted value spans two physical lines, so B is reported on line 5.
        self.assertEqual([line for line, _ in document.records], [4, 5])

    def test_ragged_rows_are_errors(self) -> None:
        _, errors = read_csv("code,label\nA\nB,Beta,extra\n")
        self.assertEqual([str(e) for e in errors],
                         ["line 2: expected 2 columns, got 1", "line 3: expected 2 columns, got 3"])

    def test_empty_and_blank_header(self) -> None:
        self.assertIn("header row is required", str(read_csv("")[1][0]))
        self.assertIn("empty column name", str(read_csv("code,,label\nA,B,C\n")[1][0]))

    def test_decode_strips_bom_and_rejects_invalid_utf8(self) -> None:
        self.assertEqual(decode_csv_bytes("\ufeffcode\n".encode()), "code\n")
        with self.assertRaises(InvalidUploadError):
            decode_csv_bytes(b"\xff\xfe")


class ImportRowsTests(unittest.TestCase):
    def test_identity_mapping(self) -> None:
        document, _ = read_csv("code,label\nA,Alpha\n")
        result = import_rows(document, codes_definition())
        self.assertEqual(result.errors, [])
        self.assertEqual(result.rows[("A",)].values, {"label": "Alpha"})

    def test_mapping_renames_columns_and_applies_transforms(self) -> None:
        document, _ = read_csv("Code,Description\n a ,  Alpha \n")
        mapping = RecordMapping(
            key={"code": FieldSpec(path="Code", transforms=("trim", "upper"))},
            values={"label": FieldSpec(path="Description", transforms=("trim",))},
        )
        result = import_rows(document, codes_definition(), mapping)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.rows[("A",)].values, {"label": "Alpha"})

    def test_key_normalisation_applies_after_transforms(self) -> None:
        definition = codes_definition(key_normalisation={"code": KeyPartRule(case="lower")})
        document, _ = read_csv("code,label\nABC,x\n")
        self.assertIn(("abc",), import_rows(document, definition).rows)

    def test_mapping_targets_must_match_table_columns(self) -> None:
        document, _ = read_csv("code,label\nA,Alpha\n")
        mapping = RecordMapping(key={"code": FieldSpec(path="code")}, values={"other": FieldSpec(path="label")})
        errors = [str(e) for e in import_rows(document, codes_definition(), mapping).errors]
        self.assertTrue(any("value targets" in e for e in errors))

    def test_header_must_contain_mapped_columns_and_nothing_else(self) -> None:
        document, _ = read_csv("code,notes\nA,n\n")
        errors = [str(e) for e in import_rows(document, codes_definition()).errors]
        self.assertIn("line 1: columns ['label'] are not in the header", errors)
        self.assertIn("line 1: header columns ['notes'] are neither key nor value columns", errors)

    def test_collects_errors_without_values_and_truncates(self) -> None:
        body = "".join(f"DUP{i % 2},x\n" for i in range(60))
        document, _ = read_csv("code,label\n" + body)
        result = import_rows(document, codes_definition())
        messages = result.error_messages()
        self.assertEqual(len(result.errors), 50)
        self.assertTrue(result.truncated)
        self.assertIn("further errors suppressed", messages[-1])
        self.assertFalse(any("DUP" in m for m in messages))

    def test_composite_key(self) -> None:
        definition = TableDefinition(name="ward_map", key_columns=("fac", "ward"), value_columns=("code",),
                                     default_value_column="code")
        document, _ = read_csv("fac,ward,code\nF1,W1,X\nF1,W2,Y\nF1,W1,Z\n")
        result = import_rows(document, definition)
        self.assertEqual(set(result.rows), {("F1", "W1"), ("F1", "W2")})
        self.assertEqual(str(result.errors[0]), "line 4: duplicate key (first seen on line 2)")


class BuildDefinitionTests(unittest.TestCase):
    def test_defaults_from_header(self) -> None:
        definition = build_definition("codes", ["code", "a", "b"], {})
        self.assertEqual(definition.key_columns, ("code",))
        self.assertEqual(definition.value_columns, ("a", "b"))
        self.assertEqual(definition.default_value_column, "a")
        self.assertFalse(definition.preload)

    def test_overrides(self) -> None:
        definition = build_definition("codes", ["x", "y", "z"], {
            "key_columns": ["x", "y"], "default_value_column": "z", "ttl_seconds": 30, "preload": True,
            "key_normalisation": {"x": {"case": "upper"}},
        })
        self.assertEqual(definition.key_columns, ("x", "y"))
        self.assertEqual(definition.ttl_seconds, 30)
        self.assertEqual(definition.rule_for("x").case, "upper")

    def test_invalid(self) -> None:
        with self.assertRaises(ValidationError):
            build_definition("codes", ["only_key"], {})
        with self.assertRaises(ValidationError):
            build_definition("codes", ["a", "b"], {"ttl_seconds": 0})


class TransformTests(unittest.TestCase):
    def test_transforms_apply_in_order(self) -> None:
        self.assertEqual(apply_transforms("  Ab ", ("trim", "upper")), "AB")
        self.assertEqual(apply_transforms("Ab", ("lower",)), "ab")
        self.assertEqual(apply_transforms(" x ", ()), " x ")


if __name__ == "__main__":
    unittest.main()
