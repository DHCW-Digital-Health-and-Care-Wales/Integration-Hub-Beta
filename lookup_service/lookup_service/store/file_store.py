"""Read-only store backed by CSV files shipped in the image.

Each `<seed_dir>/<table>.csv` becomes a table. Without a manifest entry, the first column is the key
and the remaining columns are values. `<seed_dir>/tables.json` can override this per table, e.g. to
declare composite keys, per-part normalisation, TTL and preloading:

    {"tables": {"ward_map": {"key_columns": ["sending_facility", "ward_code"],
                             "key_normalisation": {"ward_code": {"case": "upper"}}}}}

Everything is validated and loaded once at startup into immutable mappings, so lookups are lock-free
and any data problem stops the service starting rather than surfacing as wrong substitutions later.
With Cosmos configured, the same files seed tables that don't exist yet (see `seed.py`).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any

from pydantic import ValidationError

from lookup_service.csv_import import build_definition, import_rows, read_csv
from lookup_service.errors import ReadOnlyStoreError, SeedDataError
from lookup_service.keys import key_text
from lookup_service.models import Row, TableDefinition, TableRecord, TableStats, UploadInfo
from lookup_service.store.base import ReplaceResult

logger = logging.getLogger(__name__)

MANIFEST_NAME = "tables.json"
MAX_SEED_FILE_BYTES = 50 * 1024 * 1024
MANIFEST_FIELDS = frozenset(
    {"description", "key_columns", "value_columns", "default_value_column", "key_normalisation", "ttl_seconds",
     "preload"}
)
SEED_ACTOR = "seed"


@dataclass(frozen=True)
class LoadedTable:
    definition: TableDefinition
    rows: Mapping[tuple[str, ...], Row]
    source_file: str
    loaded_at: datetime

    def record(self) -> TableRecord:
        return TableRecord(
            definition=self.definition,
            stats=TableStats(row_count=len(self.rows), last_upload_at=self.loaded_at,
                             last_upload_file=self.source_file, last_upload_by=SEED_ACTOR),
        )


class FileTableStore:
    source = "file"
    writable = False

    def __init__(self, tables: Mapping[str, LoadedTable]) -> None:
        self._tables: Mapping[str, LoadedTable] = MappingProxyType(dict(tables))

    @classmethod
    def load(cls, seed_dir: Path) -> FileTableStore:
        if not seed_dir.is_dir():
            raise SeedDataError(f"Seed directory {seed_dir} does not exist")

        manifest = _read_manifest(seed_dir)
        csv_files = sorted(seed_dir.glob("*.csv"))
        orphaned = sorted(set(manifest) - {path.stem for path in csv_files})
        if orphaned:
            raise SeedDataError(f"{MANIFEST_NAME} declares tables with no CSV file: {orphaned}")

        tables = {path.stem: load_csv_table(path, manifest.get(path.stem, {})) for path in csv_files}
        if not tables:
            logger.warning("No seed CSV files found in %s; serving no tables", seed_dir)
        for table in tables.values():
            logger.info("Loaded seed table %s: %d row(s) from %s", table.definition.name, len(table.rows),
                        table.source_file)
        return cls(tables)

    @property
    def loaded_tables(self) -> list[LoadedTable]:
        return [self._tables[name] for name in sorted(self._tables)]

    async def open(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def list_tables(self) -> list[TableRecord]:
        return [table.record() for table in self.loaded_tables]

    async def get_table(self, table: str) -> TableRecord | None:
        loaded = self._tables.get(table)
        return loaded.record() if loaded else None

    async def get_row(self, table: str, key: tuple[str, ...]) -> Row | None:
        loaded = self._tables.get(table)
        return loaded.rows.get(key) if loaded else None

    async def load_rows(self, table: str) -> list[Row]:
        loaded = self._tables.get(table)
        return list(loaded.rows.values()) if loaded else []

    async def query_rows(self, table: str, search: str | None, offset: int, limit: int) -> tuple[list[Row], int]:
        loaded = self._tables.get(table)
        if loaded is None:
            return [], 0
        rows = sorted(loaded.rows.values(), key=lambda row: key_text(row.key))
        if search:
            needle = search.casefold()
            rows = [row for row in rows if needle in key_text(row.key).casefold()]
        return rows[offset:offset + limit], len(rows)

    async def replace_table(
        self, definition: TableDefinition, rows: Sequence[Row], upload: UploadInfo
    ) -> ReplaceResult:
        raise ReadOnlyStoreError("Tables are served from seed files; configure COSMOS_ENDPOINT to enable uploads",
                                 definition.name)


def _read_manifest(seed_dir: Path) -> dict[str, dict[str, Any]]:
    path = seed_dir / MANIFEST_NAME
    if not path.exists():
        return {}
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SeedDataError(f"{MANIFEST_NAME} could not be read: {exc}") from exc

    tables = content.get("tables") if isinstance(content, dict) else None
    if not isinstance(tables, dict) or not all(isinstance(entry, dict) for entry in tables.values()):
        raise SeedDataError(f'{MANIFEST_NAME} must be an object of the form {{"tables": {{"<name>": {{...}}}}}}')
    return tables


def load_csv_table(path: Path, manifest_entry: Mapping[str, Any]) -> LoadedTable:
    if path.stat().st_size > MAX_SEED_FILE_BYTES:
        raise SeedDataError(f"{path.name}: exceeds the {MAX_SEED_FILE_BYTES // (1024 * 1024)} MB seed file limit")
    _validate_manifest_entry(path.stem, manifest_entry)

    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SeedDataError(f"{path.name}: not valid UTF-8") from exc
    document, errors = read_csv(text)
    if errors:
        raise SeedDataError(f"{path.name} {errors[0]}")

    try:
        definition = build_definition(path.stem, document.header, manifest_entry)
    except ValidationError as exc:
        raise SeedDataError(f"{path.name}: invalid table definition: {exc}") from exc

    result = import_rows(document, definition)
    if result.errors:
        raise SeedDataError(f"{path.name} {result.errors[0]}")

    return LoadedTable(
        definition=definition,
        rows=MappingProxyType(result.rows),
        source_file=path.name,
        loaded_at=datetime.now(UTC),
    )


def _validate_manifest_entry(table: str, entry: Mapping[str, Any]) -> None:
    unknown_fields = sorted(set(entry) - MANIFEST_FIELDS)
    if unknown_fields:
        raise SeedDataError(f"{MANIFEST_NAME} entry for {table!r} has unknown fields {unknown_fields}")
    for field in ("key_columns", "value_columns"):
        configured = entry.get(field)
        if configured is not None and not (
            isinstance(configured, list) and all(isinstance(column, str) for column in configured)
        ):
            raise SeedDataError(f"{MANIFEST_NAME} entry for {table!r}: {field} must be a list of strings")
