"""
Generic in-memory TTL cache with stale-while-revalidate background refresh.

Extracted from ``dashboard/app.py`` so the caching engine (keys, locking,
background refresh) can be unit-tested in isolation from Flask routes and the
Azure-backed builder functions it wraps.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from typing import Any

from dashboard import config

log = logging.getLogger(__name__)

_CORE_KEYS: frozenset[str] = frozenset(
    {
        "status",
        "flows",
        "exceptions",
        "servicebus",
        "messages",
        "alarms",
        "alarm2",
        "alarm3",
    }
)
# Upper bound on total entries in cache_data so dynamic parameterised keys
# (e.g. messages_*, hl7_throughput_*, sb_metrics_*, app_history_*, trace_*)
# cannot grow memory unboundedly.
_MAX_CACHE_ENTRIES = 256


def _initial_cache_data() -> dict[str, dict[str, Any]]:
    return {key: {"data": None, "ts": 0.0} for key in _CORE_KEYS}


cache_lock = Lock()
cache_data: dict[str, dict[str, Any]] = _initial_cache_data()

_bg_refresh_in_flight: set[str] = set()
_bg_refresh_lock = Lock()

# Per-key locks prevent cold-cache stampedes: when several concurrent requests
# miss the same key at once, only one runs builder() and the rest reuse its result.
_key_locks_guard = Lock()
_key_locks: dict[str, Lock] = {}


def _get_key_lock(key: str) -> Lock:
    with _key_locks_guard:
        lock = _key_locks.get(key)
        if lock is None:
            lock = Lock()
            _key_locks[key] = lock
        return lock


def _evict_dynamic_entries_locked() -> None:
    """Drop oldest non-core cache entries when cache_data exceeds _MAX_CACHE_ENTRIES.

    Caller must hold ``cache_lock``.
    """
    if len(cache_data) <= _MAX_CACHE_ENTRIES:
        return
    dynamic_keys = [k for k in cache_data if k not in _CORE_KEYS]
    dynamic_keys.sort(key=lambda k: cache_data[k].get("ts", 0.0))
    to_remove = len(cache_data) - _MAX_CACHE_ENTRIES
    for key in dynamic_keys[:to_remove]:
        cache_data.pop(key, None)


def has_cached(key: str) -> bool:
    """Return True if *key* already has a populated value in the cache."""
    with cache_lock:
        entry = cache_data.get(key)
        return entry is not None and entry.get("data") is not None


def get_fresh(key: str, ttl: float | None = None) -> Any | None:
    """Return the cached value for *key* if present and within *ttl*, else None."""
    _ttl = ttl if ttl is not None else config.API_CACHE_TTL
    now = time.monotonic()
    with cache_lock:
        entry = cache_data.get(key)
        if entry is not None and entry.get("data") is not None and (now - entry["ts"]) <= _ttl:
            return entry["data"]
    return None


def set_cached(key: str, value: Any) -> None:
    """Store *value* directly in the cache with the current monotonic timestamp."""
    now = time.monotonic()
    with cache_lock:
        entry = cache_data.setdefault(key, {"data": None, "ts": 0.0})
        entry["data"] = value
        entry["ts"] = now
        _evict_dynamic_entries_locked()


def invalidate(*keys: str) -> None:
    """Clear cached values for the given keys so the next read rebuilds fresh data."""
    with cache_lock:
        for key in keys:
            if key in cache_data:
                cache_data[key]["data"] = None
                cache_data[key]["ts"] = 0.0


def reset_for_tests() -> None:
    """Restore the cache to its clean initial state (used by unit tests)."""
    with cache_lock:
        cache_data.clear()
        cache_data.update(_initial_cache_data())
    with _bg_refresh_lock:
        _bg_refresh_in_flight.clear()
    with _key_locks_guard:
        _key_locks.clear()


def cached(key: str, builder: Callable[[], Any], ttl: float | None = None, force: bool = False) -> Any:
    """Generic TTL cache helper. Returns cached value or calls builder() to refresh.

    The global lock is held only for the fast cache-check and the final store —
    never during the (potentially slow) Azure API call, so unrelated keys are not
    blocked. A per-key lock coalesces concurrent cold/expired rebuilds for the
    same key so duplicate Azure queries are avoided.
    """
    _ttl = ttl if ttl is not None else config.API_CACHE_TTL
    now = time.monotonic()

    # Fast path: return immediately if fresh
    if not force:
        with cache_lock:
            entry = cache_data.setdefault(key, {"data": None, "ts": 0.0})
            if (now - entry["ts"]) <= _ttl and entry["data"] is not None:
                return entry["data"]

    # Slow path: serialise rebuilds for *this* key only (singleflight)
    key_lock = _get_key_lock(key)
    with key_lock:
        if not force:
            with cache_lock:
                entry = cache_data.setdefault(key, {"data": None, "ts": 0.0})
                if (now - entry["ts"]) <= _ttl and entry["data"] is not None:
                    return entry["data"]

        new_data = builder()

        with cache_lock:
            entry = cache_data.setdefault(key, {"data": None, "ts": 0.0})
            entry["data"] = new_data
            entry["ts"] = time.monotonic()
            _evict_dynamic_entries_locked()

        return new_data


def cached_nowait(key: str, builder: Callable[[], Any], ttl: float | None = None) -> Any:
    """Stale-while-revalidate: return cached data immediately (even if stale)
    and trigger a background refresh if the entry is expired.  Only blocks on
    the very first call when there is no cached value at all.
    """
    _ttl = ttl if ttl is not None else config.API_CACHE_TTL
    now = time.monotonic()

    with cache_lock:
        entry = cache_data.setdefault(key, {"data": None, "ts": 0.0})
        cached_value = entry["data"]
        is_stale = (now - entry["ts"]) > _ttl

    if cached_value is None:
        # No data yet — must block once so the page has something to render.
        return cached(key, builder, ttl=ttl)

    if is_stale:
        # Serve stale data immediately; refresh in a background thread.
        with _bg_refresh_lock:
            if key not in _bg_refresh_in_flight:
                _bg_refresh_in_flight.add(key)

                def _refresh(k: str, b: Callable[[], Any], t: float) -> None:
                    try:
                        cached(k, b, ttl=t, force=True)
                    except Exception as exc:  # noqa: BLE001
                        log.warning("Background cache refresh failed for %r: %s", k, exc)
                    finally:
                        with _bg_refresh_lock:
                            _bg_refresh_in_flight.discard(k)

                threading.Thread(target=_refresh, args=(key, builder, _ttl), daemon=True).start()

    return cached_value


def multi_cached_nowait(
    items: Sequence[tuple[str, Callable[[], Any], float | None]],
) -> list[Any]:
    """Stale-while-revalidate for **multiple** cache keys simultaneously.

    * Hot entries  → returned instantly (no I/O).
    * Stale entries → served immediately; background thread refreshes each one.
    * Cold entries  → fetched **in parallel** via a thread pool, then returned.

    This replaces sequential ``cached_nowait`` calls on the overview page so
    that Azure Log Analytics queries for all three alarms run concurrently
    instead of one-after-the-other.
    """
    _ttl_default = config.API_CACHE_TTL
    now = time.monotonic()

    resolved: dict[str, Any] = {}
    cold: list[tuple[str, Callable[[], Any], float]] = []

    for key, builder, ttl in items:
        _ttl = ttl if ttl is not None else _ttl_default
        with cache_lock:
            entry = cache_data.setdefault(key, {"data": None, "ts": 0.0})
            cached_value = entry["data"]
            is_stale = (now - entry["ts"]) > _ttl

        if cached_value is None:
            cold.append((key, builder, _ttl))
        else:
            resolved[key] = cached_value
            if is_stale:
                with _bg_refresh_lock:
                    if key not in _bg_refresh_in_flight:
                        _bg_refresh_in_flight.add(key)

                        def _refresh(k: str, b: Callable[[], Any], t: float) -> None:
                            try:
                                cached(k, b, ttl=t, force=True)
                            except Exception as exc:  # noqa: BLE001
                                log.warning("Background cache refresh failed for %r: %s", k, exc)
                            finally:
                                with _bg_refresh_lock:
                                    _bg_refresh_in_flight.discard(k)

                        threading.Thread(target=_refresh, args=(key, builder, _ttl), daemon=True).start()

    if cold:
        # Fetch all cold entries concurrently — one thread per entry.
        with ThreadPoolExecutor(max_workers=len(cold)) as pool:
            futures = {pool.submit(cached, k, b, t, True): k for k, b, t in cold}
            for future in as_completed(futures):
                k = futures[future]
                try:
                    resolved[k] = future.result()
                except Exception as exc:  # noqa: BLE001
                    log.warning("Parallel cold fetch failed for %r: %s", k, exc)
                    resolved[k] = []

    return [resolved.get(key, []) for key, _, _ in items]


def is_cache_stale(key: str, ttl: float | None = None) -> bool:
    """Return True if the cache entry for *key* is expired (returns False for cold/unpopulated entries)."""
    _ttl = ttl if ttl is not None else config.API_CACHE_TTL
    with cache_lock:
        entry = cache_data.get(key, {"data": None, "ts": 0.0})
        if entry["data"] is None:
            return False  # first-load blocking fetch; not stale, just cold
        return (time.monotonic() - entry["ts"]) > _ttl
