from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

TABLE_NAME_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,63}$"
# Column names appear in `key.<column>` query parameters, so keep them URL- and identifier-safe.
COLUMN_NAME_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]{0,63}$"
_COLUMN_NAME_RE = re.compile(COLUMN_NAME_PATTERN)
MAX_TTL_SECONDS = 7 * 24 * 3600


class KeyPartRule(BaseModel):
    """Normalisation applied to one key part on load and on lookup, so both sides compare equal."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    trim: bool = True
    case: Literal["preserve", "upper", "lower"] = "preserve"


DEFAULT_KEY_PART_RULE = KeyPartRule()


class TableDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(pattern=TABLE_NAME_PATTERN)
    description: str = Field(default="", max_length=500)
    key_columns: tuple[str, ...] = Field(min_length=1)
    value_columns: tuple[str, ...] = Field(min_length=1)
    default_value_column: str
    key_normalisation: dict[str, KeyPartRule] = Field(default_factory=dict)
    # None means "use the service default" (LOOKUP_DEFAULT_TTL_SECONDS).
    ttl_seconds: int | None = Field(default=None, ge=1, le=MAX_TTL_SECONDS)
    # Preloaded tables are held fully in memory; others are read per key through the TTL cache.
    preload: bool = False

    @model_validator(mode="after")
    def _validate_columns(self) -> TableDefinition:
        all_columns = self.key_columns + self.value_columns
        for column in all_columns:
            if not _COLUMN_NAME_RE.fullmatch(column):
                raise ValueError(f"invalid column name {column!r}: must match {COLUMN_NAME_PATTERN}")
        if len(set(all_columns)) != len(all_columns):
            raise ValueError("column names must be unique across key_columns and value_columns")
        if self.default_value_column not in self.value_columns:
            raise ValueError(f"default_value_column {self.default_value_column!r} is not a value column")
        unknown_rules = set(self.key_normalisation) - set(self.key_columns)
        if unknown_rules:
            raise ValueError(f"key_normalisation refers to non-key columns: {sorted(unknown_rules)}")
        return self

    def rule_for(self, key_column: str) -> KeyPartRule:
        return self.key_normalisation.get(key_column, DEFAULT_KEY_PART_RULE)


class TableStats(BaseModel):
    row_count: int = 0
    last_upload_at: datetime | None = None
    last_upload_file: str | None = None
    last_upload_by: str | None = None


class TableRecord(BaseModel):
    """A table's definition plus housekeeping stats, as held by a store."""

    definition: TableDefinition
    stats: TableStats = Field(default_factory=TableStats)


@dataclass(frozen=True)
class Row:
    key: tuple[str, ...]
    values: Mapping[str, str]


@dataclass(frozen=True)
class UploadInfo:
    actor: str
    file_name: str | None


class LookupResult(BaseModel):
    table: str
    key: list[str]
    value: str
    values: dict[str, str]
    source: str
    cached: bool


class CacheStats(BaseModel):
    mode: Literal["preloaded", "ttl"]
    ttl_seconds: int | None
    entries: int
    hits: int
    misses: int


class TableSummary(BaseModel):
    name: str
    description: str
    key_columns: list[str]
    value_columns: list[str]
    default_value_column: str
    row_count: int
    source: str
    preload: bool
    ttl_seconds: int
    last_upload_at: datetime | None
    last_upload_file: str | None
    last_upload_by: str | None
    loaded_at: datetime
    cache: CacheStats


class TableDetail(TableSummary):
    key_normalisation: dict[str, KeyPartRule]


class RowOut(BaseModel):
    key: list[str]
    values: dict[str, str]


class RowsPage(BaseModel):
    table: str
    total: int
    offset: int
    limit: int
    search: str | None
    rows: list[RowOut]


class UploadResult(BaseModel):
    table: str
    row_count: int
    upserted: int
    removed: int
    duration_ms: int
    created: bool


class ErrorResponse(BaseModel):
    error: str
    detail: str
    table: str | None = None
    errors: list[str] | None = None
