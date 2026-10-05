from __future__ import annotations

from typing import Protocol

from lookup_service.models import Row, TableDefinition, TableSummary


class TableStore(Protocol):
    """Read side of lookup table storage. Phase 0 is file-backed; Phase 1 adds Cosmos."""

    source: str

    async def list_tables(self) -> list[TableSummary]: ...

    async def get_definition(self, table: str) -> TableDefinition:
        """Return the table's definition, or raise TableNotFoundError."""
        ...

    async def get_row(self, table: str, key: tuple[str, ...]) -> Row | None:
        """Return the row for a canonical key, or None. Raises TableNotFoundError for an unknown table."""
        ...
