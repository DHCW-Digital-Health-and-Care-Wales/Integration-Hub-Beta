from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from lookup_service.models import Row, TableDefinition, TableRecord, UploadInfo


@dataclass(frozen=True)
class ReplaceResult:
    upserted: int
    removed: int


class TableStore(Protocol):
    """Storage for table definitions and rows. File-backed (read-only) or Cosmos-backed."""

    source: str
    writable: bool

    async def open(self) -> None: ...

    async def close(self) -> None: ...

    async def list_tables(self) -> list[TableRecord]: ...

    async def get_table(self, table: str) -> TableRecord | None: ...

    async def get_row(self, table: str, key: tuple[str, ...]) -> Row | None:
        """Point read by canonical key. Returns None for a missing row or table."""
        ...

    async def load_rows(self, table: str) -> list[Row]:
        """Every row of a table, for preloading."""
        ...

    async def query_rows(self, table: str, search: str | None, offset: int, limit: int) -> tuple[list[Row], int]:
        """A page of rows ordered by key, optionally filtered by a case-insensitive key substring, plus the total."""
        ...

    async def replace_table(
        self, definition: TableDefinition, rows: Sequence[Row], upload: UploadInfo
    ) -> ReplaceResult:
        """Replace a table's definition and rows. Raises ReadOnlyStoreError when the store is read-only."""
        ...
