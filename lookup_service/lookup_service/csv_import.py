"""CSV parsing shared by seed loading and uploads.

Parsing produces a header plus (line number, record) pairs; `import_rows` then validates the header
against the table and maps records to canonical rows via the mapping engine. All problems are
reported with line numbers, never data values.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from lookup_service.errors import InvalidUploadError
from lookup_service.mapping.engine import DEFAULT_MAX_ERRORS, MappingResult, RecordError, map_records
from lookup_service.mapping.model import RecordMapping
from lookup_service.models import KeyPartRule, TableDefinition

HEADER_LINE = 1


@dataclass(frozen=True)
class CsvDocument:
    header: list[str]
    records: list[tuple[int, dict[str, str]]]


def decode_csv_bytes(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InvalidUploadError(f"File is not valid UTF-8 (byte offset {exc.start})") from exc


def read_csv(text: str, max_errors: int = DEFAULT_MAX_ERRORS) -> tuple[CsvDocument, list[RecordError]]:
    """Parse CSV text. Blank lines are skipped; ragged rows and header problems are errors."""
    reader = csv.reader(io.StringIO(text, newline=""))
    errors: list[RecordError] = []
    try:
        header = [column.strip() for column in next(reader, [])]
    except csv.Error as exc:
        return CsvDocument([], []), [RecordError(HEADER_LINE, f"malformed CSV: {exc}")]

    if not any(header):
        return CsvDocument([], []), [RecordError(HEADER_LINE, "file is empty; a header row is required")]
    if not all(header):
        errors.append(RecordError(HEADER_LINE, "header contains an empty column name"))
    if len(set(header)) != len(header):
        errors.append(RecordError(HEADER_LINE, "header contains duplicate column names"))

    records: list[tuple[int, dict[str, str]]] = []
    try:
        for record in reader:
            if not any(cell.strip() for cell in record):
                continue
            if len(record) != len(header):
                if len(errors) < max_errors:
                    errors.append(RecordError(reader.line_num, f"expected {len(header)} columns, got {len(record)}"))
                continue
            records.append((reader.line_num, dict(zip(header, record, strict=True))))
    except csv.Error as exc:
        errors.append(RecordError(reader.line_num, f"malformed CSV: {exc}"))
    return CsvDocument(header, records), errors


def import_rows(
    document: CsvDocument,
    definition: TableDefinition,
    mapping: RecordMapping | None = None,
) -> MappingResult:
    """Validate the header against the mapping and map every record to a canonical row."""
    mapping = mapping or RecordMapping.identity(definition)
    problems = mapping.check_targets(definition)
    source_fields = mapping.source_fields()
    missing = sorted(source_fields - set(document.header))
    if missing:
        problems.append(f"columns {missing} are not in the header")
    unmapped = sorted(set(document.header) - source_fields)
    if unmapped:
        # Explicit rather than silently dropping data someone expected to be served.
        problems.append(f"header columns {unmapped} are neither key nor value columns")
    if problems:
        return MappingResult(errors=[RecordError(HEADER_LINE, problem) for problem in problems])
    return map_records(definition, mapping, document.records)


def build_definition(name: str, header: list[str], settings: Mapping[str, Any]) -> TableDefinition:
    """Create a definition from a CSV header plus optional overrides.

    Without overrides, the first column is the key and the remaining columns are values.
    Raises pydantic.ValidationError for an invalid result.
    """
    key_columns = list(settings.get("key_columns") or header[:1])
    value_columns = list(settings.get("value_columns") or [c for c in header if c not in key_columns])
    normalisation = {
        column: rule if isinstance(rule, KeyPartRule) else KeyPartRule.model_validate(rule)
        for column, rule in (settings.get("key_normalisation") or {}).items()
    }
    return TableDefinition(
        name=name,
        description=settings.get("description") or "",
        key_columns=tuple(key_columns),
        value_columns=tuple(value_columns),
        default_value_column=settings.get("default_value_column") or (value_columns[0] if value_columns else ""),
        key_normalisation=normalisation,
        ttl_seconds=settings.get("ttl_seconds"),
        preload=bool(settings.get("preload", False)),
    )
