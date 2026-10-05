from __future__ import annotations

import asyncio
import unittest

from lookup_service.errors import SeedDataError
from lookup_service.seed import import_missing_seed_tables
from tests.helpers import REPO_SEED_DIR, MemoryTableStore, SeedDirTestCase, codes_definition, make_row


class SeedImportTests(unittest.TestCase):
    def test_imports_all_seed_tables_into_empty_store(self) -> None:
        store = MemoryTableStore()
        imported = asyncio.run(import_missing_seed_tables(store, REPO_SEED_DIR))
        self.assertEqual(sorted(imported), ["health_board_mapping", "ward_map"])
        self.assertEqual(store.records["health_board_mapping"].stats.last_upload_by, "seed")
        self.assertEqual(store.rows["health_board_mapping"][("224",)].values["health_board"], "VCC")

    def test_never_overwrites_existing_tables(self) -> None:
        store = MemoryTableStore()
        store.put_table(codes_definition(name="health_board_mapping", key_columns=("msh3",),
                                         value_columns=("health_board",), default_value_column="health_board"),
                        [make_row("224", health_board="UPLOADED")])
        imported = asyncio.run(import_missing_seed_tables(store, REPO_SEED_DIR))
        self.assertEqual(imported, ["ward_map"])
        self.assertEqual(store.rows["health_board_mapping"][("224",)].values["health_board"], "UPLOADED")

    def test_read_only_store_is_skipped(self) -> None:
        self.assertEqual(asyncio.run(import_missing_seed_tables(MemoryTableStore(writable=False), REPO_SEED_DIR)),
                         [])


class SeedValidationTests(SeedDirTestCase):
    def test_bad_seed_stops_startup(self) -> None:
        self.write_csv("codes", "code,label\nA,1\nA,2\n")
        with self.assertRaises(SeedDataError):
            asyncio.run(import_missing_seed_tables(MemoryTableStore(), self.seed_dir))

    def test_missing_seed_dir_is_skipped(self) -> None:
        self.assertEqual(asyncio.run(import_missing_seed_tables(MemoryTableStore(), self.seed_dir / "none")), [])


if __name__ == "__main__":
    unittest.main()
