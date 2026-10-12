from __future__ import annotations

import time
from collections.abc import Callable

from cachetools import TTLCache

from lookup_service.models import Row

Timer = Callable[[], float]


class TableCache:
    """Per-table TTL cache of found rows.

    All access happens on the event loop with no awaits inside these methods, so each operation is
    atomic and no lock is needed. Misses aren't cached yet (negative caching arrives in Phase 4).
    """

    def __init__(self, ttl_seconds: int, max_entries: int, timer: Timer = time.monotonic) -> None:
        self.ttl_seconds = ttl_seconds
        self._entries: TTLCache[tuple[str, ...], Row] = TTLCache(maxsize=max_entries, ttl=ttl_seconds, timer=timer)
        self.hits = 0
        self.misses = 0

    def get(self, key: tuple[str, ...]) -> Row | None:
        row = self._entries.get(key)
        if row is None:
            self.misses += 1
        else:
            self.hits += 1
        return row

    def put(self, key: tuple[str, ...], row: Row) -> None:
        self._entries[key] = row

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        self._entries.expire()
        return len(self._entries)
