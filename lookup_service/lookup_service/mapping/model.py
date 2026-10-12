"""Record mapping model: how source records become canonical rows.

Phase 1 implements the CSV subset: a field's `path` is a CSV column name and only the trim/upper/lower
transforms exist. Phase 5 extends the same model with XPath/JMESPath paths and more transforms.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from lookup_service.models import TableDefinition

Transform = Literal["trim", "upper", "lower"]


class FieldSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1, max_length=200)
    transforms: tuple[Transform, ...] = ()


class RecordMapping(BaseModel):
    """Maps each table column (target) to a field in the source record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: dict[str, FieldSpec]
    values: dict[str, FieldSpec]

    @classmethod
    def identity(cls, definition: TableDefinition) -> RecordMapping:
        """Each table column is read from the source field of the same name."""
        return cls(
            key={column: FieldSpec(path=column) for column in definition.key_columns},
            values={column: FieldSpec(path=column) for column in definition.value_columns},
        )

    def check_targets(self, definition: TableDefinition) -> list[str]:
        """Return problems where the mapping's targets don't match the table's columns."""
        problems = []
        if set(self.key) != set(definition.key_columns):
            problems.append(f"mapping key targets {sorted(self.key)} must equal key columns "
                            f"{list(definition.key_columns)}")
        if set(self.values) != set(definition.value_columns):
            problems.append(f"mapping value targets {sorted(self.values)} must equal value columns "
                            f"{list(definition.value_columns)}")
        return problems

    def source_fields(self) -> set[str]:
        return {spec.path for spec in (*self.key.values(), *self.values.values())}
