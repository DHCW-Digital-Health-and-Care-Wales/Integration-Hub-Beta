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
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from typing import Any, Callable

from dashboard import config

log = logging.getLogger(__name__)

cache_lock = Lock()
cache_data: dict = {
    "status": {"data": None, "ts": 0.0},
    "flows": {"data": None, "ts": 0.0},
    "exceptions": {"data": None, "ts": 0.0},
    "servicebus": {"data": None, "ts": 0.0},
    "messages": {"data": None, "ts": 0.0},
    "alarms": {"data": None, "ts": 0.0},
    "alarm2": {"data": None, "ts": 0.0},
    "alarm3": {"data": None, "ts": 0.0},
}

_bg_refresh_in_flight: set[str] = set()
_bg_refresh_lock = Lock()


def cached(key: str, builder: Callable[[], Any], ttl: float | None = None, force: bool = False) -> Any:
    """Generic TTL cache helper. Returns cached value or calls builder() to refresh.

    The lock is held only for the fast cache-check and the final store — never
    during the (potentially slow) Azure API call, so concurrent requests are not
    blocked waiting for a cache rebuild.
    """
    _ttl = ttl if ttl is not None else config.API_CACHE_TTL
    now = time.monotonic()

    # Fast path: return stale-check under lock, return immediately if fresh
    if not force:
        with cache_lock:
            entry = cache_data.setdefault(key, {"data": None, "ts": 0.0})
            if (now - entry["ts"]) <= _ttl and entry["data"] is not None:
                return entry["data"]

    # Slow path: call builder outside the lock so other requests aren't blocked
    new_data = builder()

    with cache_lock:
        entry = cache_data.setdefault(key, {"data": None, "ts": 0.0})
        entry["data"] = new_data
        entry["ts"] = time.monotonic()

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
    items: list[tuple[str, Callable[[], Any], float | None]],
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
