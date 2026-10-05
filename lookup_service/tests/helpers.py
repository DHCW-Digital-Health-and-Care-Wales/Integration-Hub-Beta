from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from lookup_service.config import Settings
from lookup_service.models import Row
from lookup_service.store.base import TableStore

REPO_SEED_DIR = Path(__file__).resolve().parent.parent / "seed"


def require_row(store: TableStore, table: str, key: tuple[str, ...]) -> Row:
    row = asyncio.run(store.get_row(table, key))
    if row is None:
        raise AssertionError(f"expected a row in {table!r}")
    return row


def make_settings(seed_dir: Path = REPO_SEED_DIR, environment: str = "LOCAL") -> Settings:
    return Settings(seed_dir=seed_dir, environment=environment, host="127.0.0.1", port=8080, log_level="INFO")


class SeedDirTestCase(unittest.TestCase):
    """Provides a throwaway seed directory per test."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.seed_dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write_csv(self, name: str, content: str, encoding: str = "utf-8") -> Path:
        path = self.seed_dir / f"{name}.csv"
        path.write_text(content, encoding=encoding, newline="")
        return path

    def write_manifest(self, tables: dict[str, Any]) -> None:
        (self.seed_dir / "tables.json").write_text(json.dumps({"tables": tables}), encoding="utf-8")
