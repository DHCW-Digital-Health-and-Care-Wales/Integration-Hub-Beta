"""Lookup orchestration: in-memory table registry, preloaded snapshots, TTL caches, store fallback.

Table definitions are held in memory (loaded at startup, refreshed on this replica after an upload),
so a lookup never needs a definition read. Preloaded tables are served from an immutable snapshot
that is swapped atomically on refresh; other tables go cache -> store point read -> cache.
Cross-replica invalidation arrives in Phase 4.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType

from lookup_service.cache.table_cache import TableCache, Timer
from lookup_service.errors import InvalidKeyError, KeyNotFoundError, TableNotFoundError
from lookup_service.keys import canonical_key
from lookup_service.models import (
    CacheStats,
    LookupResult,
    Row,
    TableDefinition,
    TableDetail,
    TableRecord,
    TableSummary,
)
from lookup_service.store.base import TableStore

NAMED_KEY_PREFIX = "key."


def named_key_params(table: str, params: Iterable[tuple[str, str]]) -> dict[str, str]:
    """Collect `key.<part>=value` query/form parameters, rejecting a part supplied more than once."""
    named: dict[str, str] = {}
    for name, value in params:
        if not name.startswith(NAMED_KEY_PREFIX):
            continue
        part = name[len(NAMED_KEY_PREFIX):]
        if part in named:
            raise InvalidKeyError(f"Key part {part!r} supplied more than once", table)
        named[part] = value
    return named


@dataclass(frozen=True)
class _TableState:
    record: TableRecord
    loaded_at: datetime
    snapshot: Mapping[tuple[str, ...], Row] | None
    cache: TableCache | None

    @property
    def definition(self) -> TableDefinition:
        return self.record.definition


class LookupResolver:
    def __init__(
        self,
        store: TableStore,
        default_ttl_seconds: int,
        max_entries: int,
        timer: Timer = time.monotonic,
    ) -> None:
        self.store = store
        self._default_ttl_seconds = default_ttl_seconds
        self._max_entries = max_entries
        self._timer = timer
        self._tables: dict[str, _TableState] = {}
        # Uploads are rare; serialising them on a replica stops two replaces of one table interleaving.
        self.upload_lock = asyncio.Lock()

    async def start(self) -> None:
        """Load every table definition and preload snapshots. Readiness should wait for this."""
        tables: dict[str, _TableState] = {}
        for record in await self.store.list_tables():
            tables[record.definition.name] = await self._build_state(record)
        self._tables = tables

    async def refresh_table(self, table: str) -> None:
        """Re-read one table after it changed (e.g. an upload): new definition, fresh cache or snapshot."""
        record = await self.store.get_table(table)
        if record is None:
            self._tables.pop(table, None)
            return
        self._tables[table] = await self._build_state(record)

    def has_table(self, table: str) -> bool:
        return table in self._tables

    def definition(self, table: str) -> TableDefinition:
        return self._state(table).definition

    async def lookup(
        self,
        table: str,
        positional: Sequence[str] = (),
        named: Mapping[str, str] | None = None,
    ) -> LookupResult:
        state = self._state(table)
        definition = state.definition
        key = canonical_key(definition, positional, named)

        cached = True
        if state.snapshot is not None:
            row = state.snapshot.get(key)
        elif state.cache is not None:
            row = state.cache.get(key)
            if row is None:
                cached = False
                row = await self.store.get_row(table, key)
                if row is not None:
                    state.cache.put(key, row)
        else:  # pragma: no cover - _build_state always sets one of them
            raise RuntimeError(f"Table {table!r} has neither a snapshot nor a cache")

        if row is None:
            # Deliberately no key values in the message: it can end up in caller logs.
            raise KeyNotFoundError(f"No row for the supplied key in table {table!r}", table)
        return LookupResult(
            table=table,
            key=list(key),
            value=row.values[definition.default_value_column],
            values=dict(row.values),
            source=self.store.source,
            cached=cached,
        )

    def summaries(self) -> list[TableSummary]:
        return [self._summary(state) for _, state in sorted(self._tables.items())]

    def detail(self, table: str) -> TableDetail:
        state = self._state(table)
        return TableDetail(**self._summary(state).model_dump(),
                           key_normalisation=dict(state.definition.key_normalisation))

    def _state(self, table: str) -> _TableState:
        state = self._tables.get(table)
        if state is None:
            raise TableNotFoundError(f"Table {table!r} does not exist", table)
        return state

    def _ttl_for(self, definition: TableDefinition) -> int:
        return definition.ttl_seconds or self._default_ttl_seconds

    async def _build_state(self, record: TableRecord) -> _TableState:
        definition = record.definition
        loaded_at = datetime.now(UTC)
        if definition.preload:
            rows = await self.store.load_rows(definition.name)
            snapshot = MappingProxyType({row.key: row for row in rows})
            return _TableState(record=record, loaded_at=loaded_at, snapshot=snapshot, cache=None)
        cache = TableCache(self._ttl_for(definition), self._max_entries, self._timer)
        return _TableState(record=record, loaded_at=loaded_at, snapshot=None, cache=cache)

    def _summary(self, state: _TableState) -> TableSummary:
        definition, stats = state.definition, state.record.stats
        if state.snapshot is not None:
            cache = CacheStats(mode="preloaded", ttl_seconds=None, entries=len(state.snapshot), hits=0, misses=0)
        elif state.cache is not None:
            cache = CacheStats(mode="ttl", ttl_seconds=state.cache.ttl_seconds, entries=len(state.cache),
                               hits=state.cache.hits, misses=state.cache.misses)
        else:  # pragma: no cover - _build_state always sets one of them
            raise RuntimeError(f"Table {definition.name!r} has neither a snapshot nor a cache")
        return TableSummary(
            name=definition.name,
            description=definition.description,
            key_columns=list(definition.key_columns),
            value_columns=list(definition.value_columns),
            default_value_column=definition.default_value_column,
            row_count=stats.row_count,
            source=self.store.source,
            preload=definition.preload,
            ttl_seconds=self._ttl_for(definition),
            last_upload_at=stats.last_upload_at,
            last_upload_file=stats.last_upload_file,
            last_upload_by=stats.last_upload_by,
            loaded_at=state.loaded_at,
            cache=cache,
        )
