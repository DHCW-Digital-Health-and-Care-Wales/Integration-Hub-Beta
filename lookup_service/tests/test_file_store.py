from __future__ import annotations

import asyncio
import unittest

from lookup_service.errors import SeedDataError, TableNotFoundError
from lookup_service.store.file_store import MAX_SEED_FILE_BYTES, FileTableStore
from tests.helpers import REPO_SEED_DIR, SeedDirTestCase, require_row


class RepoSeedTests(unittest.TestCase):
    """The seed data shipped in the image must always load."""

    def test_repo_seed_loads(self) -> None:
        store = FileTableStore.load(REPO_SEED_DIR)
        tables = {t.name: t for t in asyncio.run(store.list_tables())}
        self.assertEqual(tables["health_board_mapping"].row_count, 4)
        self.assertEqual(tables["ward_map"].key_columns, ["sending_facility", "ward_code"])

    def test_health_board_mapping_matches_chemo_pid_mapper(self) -> None:
        store = FileTableStore.load(REPO_SEED_DIR)
        expected = {"224": "VCC", "212": "BCUCC", "192": "SWWCC", "245": "SEWCC"}
        for code, board in expected.items():
            row = require_row(store, "health_board_mapping", (code,))
            self.assertEqual(row.values["health_board"], board)


class FileTableStoreLoadTests(SeedDirTestCase):
    def test_first_column_is_key_by_default(self) -> None:
        self.write_csv("codes", "code,label,extra\nA,Alpha,x\n")
        store = FileTableStore.load(self.seed_dir)
        definition = asyncio.run(store.get_definition("codes"))
        self.assertEqual(definition.key_columns, ("code",))
        self.assertEqual(definition.value_columns, ("label", "extra"))
        self.assertEqual(definition.default_value_column, "label")

    def test_manifest_declares_composite_key_and_normalisation(self) -> None:
        self.write_csv("ward_map", "fac,ward,code\nfac1,w1,X\n")
        self.write_manifest({"ward_map": {"key_columns": ["fac", "ward"],
                                          "key_normalisation": {"fac": {"case": "upper"},
                                                                "ward": {"case": "upper"}}}})
        store = FileTableStore.load(self.seed_dir)
        require_row(store, "ward_map", ("FAC1", "W1"))

    def test_tolerates_bom_and_blank_lines_and_trims_header(self) -> None:
        self.write_csv("codes", " code , label \n\nA,Alpha\n,\nB,Beta\n", encoding="utf-8-sig")
        store = FileTableStore.load(self.seed_dir)
        self.assertEqual(asyncio.run(store.list_tables())[0].row_count, 2)
        definition = asyncio.run(store.get_definition("codes"))
        self.assertEqual(definition.key_columns, ("code",))

    def test_quoted_values_with_commas(self) -> None:
        self.write_csv("codes", 'code,label\nA,"Alpha, the first"\n')
        store = FileTableStore.load(self.seed_dir)
        row = require_row(store, "codes", ("A",))
        self.assertEqual(row.values["label"], "Alpha, the first")

    def test_rows_are_immutable(self) -> None:
        self.write_csv("codes", "code,label\nA,Alpha\n")
        store = FileTableStore.load(self.seed_dir)
        row = require_row(store, "codes", ("A",))
        with self.assertRaises(TypeError):
            row.values["label"] = "changed"  # type: ignore[index]

    def test_empty_seed_dir_loads_no_tables(self) -> None:
        store = FileTableStore.load(self.seed_dir)
        self.assertEqual(asyncio.run(store.list_tables()), [])

    def test_unknown_table_raises(self) -> None:
        store = FileTableStore.load(self.seed_dir)
        with self.assertRaises(TableNotFoundError):
            asyncio.run(store.get_row("missing", ("A",)))


class FileTableStoreValidationTests(SeedDirTestCase):
    def assert_load_fails(self, message: str) -> None:
        with self.assertRaisesRegex(SeedDataError, message):
            FileTableStore.load(self.seed_dir)

    def test_missing_seed_dir(self) -> None:
        with self.assertRaisesRegex(SeedDataError, "does not exist"):
            FileTableStore.load(self.seed_dir / "nope")

    def test_empty_file(self) -> None:
        self.write_csv("codes", "")
        self.assert_load_fails("header row is required")

    def test_duplicate_key_reports_lines_not_values(self) -> None:
        self.write_csv("codes", "code,label\nSECRET,Alpha\nSECRET,Beta\n")
        with self.assertRaises(SeedDataError) as ctx:
            FileTableStore.load(self.seed_dir)
        self.assertIn("line 3: duplicate key (first seen on line 2)", str(ctx.exception))
        self.assertNotIn("SECRET", str(ctx.exception))

    def test_duplicate_after_normalisation(self) -> None:
        # " a " and "A" collide once the key part is trimmed and upper-cased.
        self.write_csv("codes", "code,label\n a ,Alpha\nA,Beta\n")
        self.write_manifest({"codes": {"key_normalisation": {"code": {"case": "upper"}}}})
        self.assert_load_fails("duplicate key")

    def test_wrong_column_count(self) -> None:
        self.write_csv("codes", "code,label\nA,Alpha,extra\n")
        self.assert_load_fails("line 2: expected 2 columns, got 3")

    def test_empty_key_part(self) -> None:
        self.write_csv("codes", "code,label\n  ,Alpha\n")
        self.assert_load_fails("line 2: empty key part")

    def test_duplicate_header(self) -> None:
        self.write_csv("codes", "code,code\nA,B\n")
        self.assert_load_fails("duplicate column names")

    def test_key_only_file_has_no_value_columns(self) -> None:
        self.write_csv("codes", "code\nA\n")
        self.assert_load_fails("invalid table definition")

    def test_invalid_table_name_from_file_name(self) -> None:
        self.write_csv("Bad Name", "code,label\nA,Alpha\n")
        self.assert_load_fails("invalid table definition")

    def test_manifest_without_csv(self) -> None:
        self.write_manifest({"ghost": {"key_columns": ["a"]}})
        self.assert_load_fails("no CSV file")

    def test_manifest_unknown_field(self) -> None:
        self.write_csv("codes", "code,label\nA,Alpha\n")
        self.write_manifest({"codes": {"key_colums": ["code"]}})
        self.assert_load_fails("unknown fields")

    def test_manifest_key_columns_must_be_list(self) -> None:
        self.write_csv("codes", "code,label\nA,Alpha\n")
        self.write_manifest({"codes": {"key_columns": "code"}})
        self.assert_load_fails("must be a list of strings")

    def test_manifest_column_not_in_header(self) -> None:
        self.write_csv("codes", "code,label\nA,Alpha\n")
        self.write_manifest({"codes": {"key_columns": ["code"], "value_columns": ["missing"]}})
        self.assert_load_fails(r"\['missing'\] are not in the header")

    def test_unmapped_header_column(self) -> None:
        self.write_csv("codes", "code,label,notes\nA,Alpha,n\n")
        self.write_manifest({"codes": {"value_columns": ["label"]}})
        self.assert_load_fails(r"\['notes'\] are neither key nor value columns")

    def test_invalid_manifest_json(self) -> None:
        (self.seed_dir / "tables.json").write_text("{not json", encoding="utf-8")
        self.assert_load_fails("could not be read")

    def test_manifest_wrong_shape(self) -> None:
        (self.seed_dir / "tables.json").write_text('{"tables": []}', encoding="utf-8")
        self.assert_load_fails("must be an object")

    def test_oversized_file(self) -> None:
        path = self.write_csv("codes", "code,label\n")
        with path.open("ab") as handle:
            handle.truncate(MAX_SEED_FILE_BYTES + 1)
        self.assert_load_fails("seed file limit")


if __name__ == "__main__":
    unittest.main()
