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


class KeyPartRule(BaseModel):
    """Normalisation applied to one key part on load and on lookup, so both sides compare equal."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    trim: bool = True
    case: Literal["preserve", "upper", "lower"] = "preserve"


DEFAULT_KEY_PART_RULE = KeyPartRule()


class TableDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(pattern=TABLE_NAME_PATTERN)
    description: str = ""
    key_columns: tuple[str, ...] = Field(min_length=1)
    value_columns: tuple[str, ...] = Field(min_length=1)
    default_value_column: str
    key_normalisation: dict[str, KeyPartRule] = Field(default_factory=dict)

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


@dataclass(frozen=True)
class Row:
    key: tuple[str, ...]
    values: Mapping[str, str]


class LookupResult(BaseModel):
    table: str
    key: list[str]
    value: str
    values: dict[str, str]
    source: str
    cached: bool


class TableSummary(BaseModel):
    name: str
    description: str
    key_columns: list[str]
    value_columns: list[str]
    default_value_column: str
    row_count: int
    source: str
    loaded_at: datetime


class ErrorResponse(BaseModel):
    error: str
    detail: str
    table: str | None = None
