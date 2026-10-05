from __future__ import annotations

import asyncio
import dataclasses
import json
import tempfile
import unittest
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any

from lookup_service.config import Settings
from lookup_service.errors import BackendUnavailableError, ReadOnlyStoreError
from lookup_service.keys import key_text
from lookup_service.models import Row, TableDefinition, TableRecord, TableStats, UploadInfo
from lookup_service.store.base import ReplaceResult, TableStore

REPO_SEED_DIR = Path(__file__).resolve().parent.parent / "seed"


def make_settings(seed_dir: Path = REPO_SEED_DIR, environment: str = "LOCAL", **overrides: Any) -> Settings:
    settings = Settings(seed_dir=seed_dir, environment=environment, host="127.0.0.1", port=8080, log_level="INFO")
    return dataclasses.replace(settings, **overrides)


def make_row(*key: str, **values: str) -> Row:
    return Row(key=tuple(key), values=MappingProxyType(dict(values)))


def require_row(store: TableStore, table: str, key: tuple[str, ...]) -> Row:
    row = asyncio.run(store.get_row(table, key))
    if row is None:
        raise AssertionError(f"expected a row in {table!r}")
    return row


def require_table(store: TableStore, table: str) -> TableRecord:
    record = asyncio.run(store.get_table(table))
    if record is None:
        raise AssertionError(f"expected table {table!r}")
    return record


class MemoryTableStore:
    """In-memory TableStore test double that counts point reads."""

    source = "memory"

    def __init__(self, writable: bool = True) -> None:
        self.writable = writable
        self.records: dict[str, TableRecord] = {}
        self.rows: dict[str, dict[tuple[str, ...], Row]] = {}
        self.get_row_calls = 0
        self.load_rows_calls = 0
        self.fail_reads = False
        self.opened = False
        self.closed = False

    def put_table(self, definition: TableDefinition, rows: Iterable[Row]) -> None:
        self.rows[definition.name] = {row.key: row for row in rows}
        self.records[definition.name] = TableRecord(
            definition=definition, stats=TableStats(row_count=len(self.rows[definition.name]))
        )

    async def open(self) -> None:
        self.opened = True

    async def close(self) -> None:
        self.closed = True

    async def list_tables(self) -> list[TableRecord]:
        return [self.records[name] for name in sorted(self.records)]

    async def get_table(self, table: str) -> TableRecord | None:
        return self.records.get(table)

    async def get_row(self, table: str, key: tuple[str, ...]) -> Row | None:
        self.get_row_calls += 1
        if self.fail_reads:
            raise BackendUnavailableError("simulated outage", table)
        return self.rows.get(table, {}).get(key)

    async def load_rows(self, table: str) -> list[Row]:
        self.load_rows_calls += 1
        return list(self.rows.get(table, {}).values())

    async def query_rows(self, table: str, search: str | None, offset: int, limit: int) -> tuple[list[Row], int]:
        rows = sorted(self.rows.get(table, {}).values(), key=lambda row: key_text(row.key))
        if search:
            rows = [row for row in rows if search.casefold() in key_text(row.key).casefold()]
        return rows[offset:offset + limit], len(rows)

    async def replace_table(
        self, definition: TableDefinition, rows: Sequence[Row], upload: UploadInfo
    ) -> ReplaceResult:
        if not self.writable:
            raise ReadOnlyStoreError("read-only", definition.name)
        existing = set(self.rows.get(definition.name, {}))
        new_rows = {row.key: row for row in rows}
        self.rows[definition.name] = new_rows
        self.records[definition.name] = TableRecord(
            definition=definition,
            stats=TableStats(row_count=len(new_rows), last_upload_at=datetime.now(UTC),
                             last_upload_file=upload.file_name, last_upload_by=upload.actor),
        )
        return ReplaceResult(upserted=len(new_rows), removed=len(existing - set(new_rows)))


def codes_definition(**overrides: Any) -> TableDefinition:
    fields: dict[str, Any] = {"name": "codes", "key_columns": ("code",), "value_columns": ("label",),
                              "default_value_column": "label"}
    fields.update(overrides)
    return TableDefinition(**fields)


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
