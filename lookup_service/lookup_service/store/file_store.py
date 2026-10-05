"""Read-only store backed by CSV files shipped in the image (Phase 0).

Each `<seed_dir>/<table>.csv` becomes a table. Without a manifest entry, the first column is the key
and the remaining columns are values. `<seed_dir>/tables.json` can override this per table, e.g. to
declare composite keys and per-part normalisation:

    {"tables": {"ward_map": {"key_columns": ["sending_facility", "ward_code"],
                             "key_normalisation": {"ward_code": {"case": "upper"}}}}}

Everything is validated and loaded once at startup into immutable mappings, so lookups are lock-free
and any data problem stops the service starting rather than surfacing as wrong substitutions later.
"""

from __future__ import annotations

import csv
import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any

from pydantic import ValidationError

from lookup_service.errors import SeedDataError, TableNotFoundError
from lookup_service.keys import normalise_part
from lookup_service.models import Row, TableDefinition, TableSummary

logger = logging.getLogger(__name__)

MANIFEST_NAME = "tables.json"
MAX_SEED_FILE_BYTES = 50 * 1024 * 1024
MANIFEST_FIELDS = frozenset(
    {"description", "key_columns", "value_columns", "default_value_column", "key_normalisation"}
)


@dataclass(frozen=True)
class LoadedTable:
    definition: TableDefinition
    rows: Mapping[tuple[str, ...], Row]
    source_file: str
    loaded_at: datetime


class FileTableStore:
    source = "file"

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
            logger.info("Loaded table %s: %d row(s) from %s", table.definition.name, len(table.rows),
                        table.source_file)
        return cls(tables)

    async def list_tables(self) -> list[TableSummary]:
        return [
            TableSummary(
                name=name,
                description=table.definition.description,
                key_columns=list(table.definition.key_columns),
                value_columns=list(table.definition.value_columns),
                default_value_column=table.definition.default_value_column,
                row_count=len(table.rows),
                source=f"{self.source}:{table.source_file}",
                loaded_at=table.loaded_at,
            )
            for name, table in sorted(self._tables.items())
        ]

    async def get_definition(self, table: str) -> TableDefinition:
        return self._get_table(table).definition

    async def get_row(self, table: str, key: tuple[str, ...]) -> Row | None:
        return self._get_table(table).rows.get(key)

    def _get_table(self, table: str) -> LoadedTable:
        loaded = self._tables.get(table)
        if loaded is None:
            raise TableNotFoundError(f"Table {table!r} does not exist", table)
        return loaded


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

    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        header = [column.strip() for column in next(reader, [])]
        if not header:
            raise SeedDataError(f"{path.name}: file is empty; a header row is required")
        definition = _build_definition(path, header, manifest_entry)
        rows = _read_rows(path, reader, header, definition)

    return LoadedTable(
        definition=definition,
        rows=MappingProxyType(rows),
        source_file=path.name,
        loaded_at=datetime.now(UTC),
    )


def _build_definition(path: Path, header: list[str], entry: Mapping[str, Any]) -> TableDefinition:
    if len(set(header)) != len(header):
        raise SeedDataError(f"{path.name}: header contains duplicate column names")
    unknown_fields = sorted(set(entry) - MANIFEST_FIELDS)
    if unknown_fields:
        raise SeedDataError(f"{MANIFEST_NAME} entry for {path.stem!r} has unknown fields {unknown_fields}")
    for field in ("key_columns", "value_columns"):
        configured = entry.get(field)
        if configured is not None and not (
            isinstance(configured, list) and all(isinstance(column, str) for column in configured)
        ):
            raise SeedDataError(f"{MANIFEST_NAME} entry for {path.stem!r}: {field} must be a list of strings")

    key_columns = list(entry.get("key_columns") or header[:1])
    value_columns = list(entry.get("value_columns") or [c for c in header if c not in key_columns])
    try:
        definition = TableDefinition(
            name=path.stem,
            description=entry.get("description", ""),
            key_columns=tuple(key_columns),
            value_columns=tuple(value_columns),
            default_value_column=entry.get("default_value_column") or (value_columns[0] if value_columns else ""),
            key_normalisation=entry.get("key_normalisation", {}),
        )
    except ValidationError as exc:
        raise SeedDataError(f"{path.name}: invalid table definition: {exc}") from exc

    mapped = set(definition.key_columns) | set(definition.value_columns)
    missing = sorted(mapped - set(header))
    if missing:
        raise SeedDataError(f"{path.name}: columns {missing} are not in the header")
    unmapped = sorted(set(header) - mapped)
    if unmapped:
        # Explicit rather than silently dropping data someone expected to be served.
        raise SeedDataError(f"{path.name}: header columns {unmapped} are neither key nor value columns")
    return definition


def _read_rows(
    path: Path, reader: Any, header: list[str], definition: TableDefinition
) -> dict[tuple[str, ...], Row]:
    key_indexes = [header.index(column) for column in definition.key_columns]
    value_indexes = {column: header.index(column) for column in definition.value_columns}
    rules = [definition.rule_for(column) for column in definition.key_columns]
    rows: dict[tuple[str, ...], Row] = {}
    first_seen: dict[tuple[str, ...], int] = {}

    for record in reader:
        line = reader.line_num
        if not any(cell.strip() for cell in record):
            continue
        if len(record) != len(header):
            raise SeedDataError(f"{path.name} line {line}: expected {len(header)} columns, got {len(record)}")

        key = tuple(normalise_part(record[index], rule) for index, rule in zip(key_indexes, rules, strict=True))
        if not all(key):
            raise SeedDataError(f"{path.name} line {line}: empty key part")
        if key in rows:
            # Line numbers only - never echo data values into logs or errors.
            raise SeedDataError(f"{path.name} line {line}: duplicate key (first seen on line {first_seen[key]})")

        rows[key] = Row(key=key, values=MappingProxyType({c: record[i] for c, i in value_indexes.items()}))
        first_seen[key] = line
    return rows
