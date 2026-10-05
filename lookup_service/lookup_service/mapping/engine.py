"""Turns source records into canonical rows, collecting per-record errors rather than stopping at the first."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from lookup_service.keys import normalise_part
from lookup_service.mapping.model import RecordMapping
from lookup_service.mapping.transforms import apply_transforms
from lookup_service.models import Row, TableDefinition

DEFAULT_MAX_ERRORS = 50


@dataclass(frozen=True)
class RecordError:
    line: int
    message: str

    def __str__(self) -> str:
        return f"line {self.line}: {self.message}"


@dataclass
class MappingResult:
    rows: dict[tuple[str, ...], Row] = field(default_factory=dict)
    errors: list[RecordError] = field(default_factory=list)
    truncated: bool = False

    def error_messages(self) -> list[str]:
        messages = [str(error) for error in self.errors]
        if self.truncated:
            messages.append(f"... further errors suppressed after the first {len(self.errors)}")
        return messages


def map_records(
    definition: TableDefinition,
    mapping: RecordMapping,
    records: Iterable[tuple[int, Mapping[str, str]]],
    max_errors: int = DEFAULT_MAX_ERRORS,
) -> MappingResult:
    """Map (line number, record) pairs to rows keyed by canonical key.

    Key parts get the mapping's transforms and then the table's key normalisation, the same
    normalisation applied on lookup. Errors carry line numbers only, never data values.
    """
    result = MappingResult()
    first_seen: dict[tuple[str, ...], int] = {}

    def add_error(line: int, message: str) -> None:
        if len(result.errors) < max_errors:
            result.errors.append(RecordError(line, message))
        else:
            result.truncated = True

    for line, record in records:
        key_parts: list[str] = []
        for column in definition.key_columns:
            spec = mapping.key[column]
            raw = record.get(spec.path)
            if raw is None:
                add_error(line, f"missing field {spec.path!r}")
                break
            part = normalise_part(apply_transforms(raw, spec.transforms), definition.rule_for(column))
            if not part:
                add_error(line, f"empty key part {column!r}")
                break
            key_parts.append(part)
        if len(key_parts) != len(definition.key_columns):
            continue

        key = tuple(key_parts)
        if key in first_seen:
            add_error(line, f"duplicate key (first seen on line {first_seen[key]})")
            continue

        values: dict[str, str] = {}
        for column in definition.value_columns:
            spec = mapping.values[column]
            raw = record.get(spec.path)
            if raw is None:
                add_error(line, f"missing field {spec.path!r}")
                break
            values[column] = apply_transforms(raw, spec.transforms)
        if len(values) != len(definition.value_columns):
            continue

        first_seen[key] = line
        result.rows[key] = Row(key=key, values=MappingProxyType(values))
    return result
