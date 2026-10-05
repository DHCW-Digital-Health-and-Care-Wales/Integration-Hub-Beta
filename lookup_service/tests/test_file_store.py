from __future__ import annotations

import asyncio
import unittest

from lookup_service.errors import ReadOnlyStoreError, SeedDataError
from lookup_service.models import UploadInfo
from lookup_service.store.file_store import MAX_SEED_FILE_BYTES, FileTableStore
from tests.helpers import REPO_SEED_DIR, SeedDirTestCase, require_row, require_table


class RepoSeedTests(unittest.TestCase):
    """The seed data shipped in the image must always load."""

    def test_repo_seed_loads(self) -> None:
        store = FileTableStore.load(REPO_SEED_DIR)
        records = {r.definition.name: r for r in asyncio.run(store.list_tables())}
        self.assertEqual(records["health_board_mapping"].stats.row_count, 4)
        self.assertTrue(records["health_board_mapping"].definition.preload)
        self.assertEqual(records["ward_map"].definition.key_columns, ("sending_facility", "ward_code"))

    def test_health_board_mapping_matches_chemo_pid_mapper(self) -> None:
        store = FileTableStore.load(REPO_SEED_DIR)
        expected = {"224": "VCC", "212": "BCUCC", "192": "SWWCC", "245": "SEWCC"}
        for code, board in expected.items():
            row = require_row(store, "health_board_mapping", (code,))
            self.assertEqual(row.values["health_board"], board)


class FileTableStoreLoadTests(SeedDirTestCase):
    def load(self) -> FileTableStore:
        return FileTableStore.load(self.seed_dir)

    def test_first_column_is_key_by_default(self) -> None:
        self.write_csv("codes", "code,label,extra\nA,Alpha,x\n")
        record = require_table(self.load(), "codes")
        self.assertEqual(record.definition.key_columns, ("code",))
        self.assertEqual(record.definition.value_columns, ("label", "extra"))
        self.assertEqual(record.definition.default_value_column, "label")
        self.assertEqual(record.stats.last_upload_by, "seed")

    def test_manifest_declares_composite_key_normalisation_ttl_and_preload(self) -> None:
        self.write_csv("ward_map", "fac,ward,code\nfac1,w1,X\n")
        self.write_manifest({"ward_map": {"key_columns": ["fac", "ward"], "ttl_seconds": 60, "preload": True,
                                          "key_normalisation": {"fac": {"case": "upper"},
                                                                "ward": {"case": "upper"}}}})
        store = self.load()
        require_row(store, "ward_map", ("FAC1", "W1"))
        record = require_table(store, "ward_map")
        self.assertEqual(record.definition.ttl_seconds, 60)
        self.assertTrue(record.definition.preload)

    def test_tolerates_bom_and_blank_lines_and_trims_header(self) -> None:
        self.write_csv("codes", " code , label \n\nA,Alpha\n,\nB,Beta\n", encoding="utf-8-sig")
        records = asyncio.run(self.load().list_tables())
        self.assertEqual(records[0].stats.row_count, 2)
        self.assertEqual(records[0].definition.key_columns, ("code",))

    def test_quoted_values_with_commas(self) -> None:
        self.write_csv("codes", 'code,label\nA,"Alpha, the first"\n')
        self.assertEqual(require_row(self.load(), "codes", ("A",)).values["label"], "Alpha, the first")

    def test_rows_are_immutable(self) -> None:
        self.write_csv("codes", "code,label\nA,Alpha\n")
        row = require_row(self.load(), "codes", ("A",))
        with self.assertRaises(TypeError):
            row.values["label"] = "changed"  # type: ignore[index]

    def test_empty_seed_dir_loads_no_tables(self) -> None:
        self.assertEqual(asyncio.run(self.load().list_tables()), [])

    def test_unknown_table_reads_return_nothing(self) -> None:
        store = self.load()
        self.assertIsNone(asyncio.run(store.get_row("missing", ("A",))))
        self.assertIsNone(asyncio.run(store.get_table("missing")))
        self.assertEqual(asyncio.run(store.load_rows("missing")), [])

    def test_query_rows_searches_keys_and_pages(self) -> None:
        self.write_csv("codes", "code,label\nA1,x\nB1,y\nA2,z\n")
        store = self.load()
        rows, total = asyncio.run(store.query_rows("codes", "a", 0, 1))
        self.assertEqual(total, 2)
        self.assertEqual([row.key for row in rows], [("A1",)])
        rows, _ = asyncio.run(store.query_rows("codes", None, 1, 10))
        self.assertEqual([row.key for row in rows], [("A2",), ("B1",)])

    def test_is_read_only(self) -> None:
        self.write_csv("codes", "code,label\nA,Alpha\n")
        store = self.load()
        record = require_table(store, "codes")
        self.assertFalse(store.writable)
        with self.assertRaises(ReadOnlyStoreError):
            asyncio.run(store.replace_table(record.definition, [], UploadInfo("me", None)))


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

    def test_invalid_normalisation_rule(self) -> None:
        self.write_csv("codes", "code,label\nA,Alpha\n")
        self.write_manifest({"codes": {"key_normalisation": {"code": {"case": "shouty"}}}})
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

    def test_not_utf8(self) -> None:
        (self.seed_dir / "codes.csv").write_bytes(b"code,label\nA,\xff\n")
        self.assert_load_fails("not valid UTF-8")

    def test_oversized_file(self) -> None:
        path = self.write_csv("codes", "code,label\n")
        with path.open("ab") as handle:
            handle.truncate(MAX_SEED_FILE_BYTES + 1)
        self.assert_load_fails("seed file limit")


if __name__ == "__main__":
    unittest.main()
