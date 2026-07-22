"""
Unit tests for dashboard.services.cache — the generic TTL / stale-while-
revalidate cache engine extracted from dashboard/app.py.
"""

from __future__ import annotations

import time
from unittest.mock import patch

from dashboard.services import cache


def _reset_cache_entry(*keys: str) -> None:
    """Remove only the test-specific keys, leaving app-wide cache keys intact.

    ``cache.cache_data`` is a shared module-level dict also relied on by
    dashboard.app routes (e.g. ``_cache_data["alarm3"]``), so tests must not
    clear the whole dict — only clean up the keys they created.
    """
    for key in keys:
        cache.cache_data.pop(key, None)


class TestCached:
    def teardown_method(self) -> None:
        _reset_cache_entry("k1", "k2", "k3", "k4")

    def test_calls_builder_and_stores_result_when_cold(self) -> None:
        builder = lambda: "fresh-value"  # noqa: E731
        result = cache.cached("k1", builder, ttl=60)
        assert result == "fresh-value"
        assert cache.cache_data["k1"]["data"] == "fresh-value"

    def test_returns_cached_value_within_ttl_without_calling_builder(self) -> None:
        calls = []

        def builder() -> str:
            calls.append(1)
            return "value"

        cache.cached("k2", builder, ttl=60)
        cache.cached("k2", builder, ttl=60)
        assert len(calls) == 1

    def test_force_bypasses_ttl_and_rebuilds(self) -> None:
        calls = []

        def builder() -> str:
            calls.append(1)
            return f"value-{len(calls)}"

        cache.cached("k3", builder, ttl=60)
        result = cache.cached("k3", builder, ttl=60, force=True)
        assert len(calls) == 2
        assert result == "value-2"

    def test_rebuilds_after_ttl_expiry(self) -> None:
        calls = []

        def builder() -> str:
            calls.append(1)
            return "value"

        cache.cached("k4", builder, ttl=0.01)
        time.sleep(0.02)
        cache.cached("k4", builder, ttl=0.01)
        assert len(calls) == 2


class TestCachedNowait:
    def teardown_method(self) -> None:
        _reset_cache_entry("k5", "k6", "k7")

    def test_blocks_and_builds_on_first_call_when_cold(self) -> None:
        result = cache.cached_nowait("k5", lambda: "first-value", ttl=60)
        assert result == "first-value"

    def test_returns_stale_value_immediately_and_schedules_refresh(self) -> None:
        cache.cached("k6", lambda: "stale-value", ttl=0.01)
        time.sleep(0.02)

        with patch("dashboard.services.cache.threading.Thread") as mock_thread:
            result = cache.cached_nowait("k6", lambda: "new-value", ttl=0.01)

        assert result == "stale-value"
        mock_thread.assert_called_once()

    def test_returns_fresh_value_without_scheduling_refresh(self) -> None:
        cache.cached("k7", lambda: "fresh-value", ttl=60)

        with patch("dashboard.services.cache.threading.Thread") as mock_thread:
            result = cache.cached_nowait("k7", lambda: "unused", ttl=60)

        assert result == "fresh-value"
        mock_thread.assert_not_called()


class TestIsCacheStale:
    def teardown_method(self) -> None:
        _reset_cache_entry("never-seen", "k8", "k9")

    def test_false_when_never_populated(self) -> None:
        assert cache.is_cache_stale("never-seen") is False

    def test_false_when_fresh(self) -> None:
        cache.cached("k8", lambda: "value", ttl=60)
        assert cache.is_cache_stale("k8", ttl=60) is False

    def test_true_when_expired(self) -> None:
        cache.cached("k9", lambda: "value", ttl=0.01)
        time.sleep(0.02)
        assert cache.is_cache_stale("k9", ttl=0.01) is True


class TestMultiCachedNowait:
    def teardown_method(self) -> None:
        _reset_cache_entry("m1", "m2", "m3")

    def test_fetches_cold_entries_in_parallel_and_preserves_order(self) -> None:
        results = cache.multi_cached_nowait(
            [
                ("m1", lambda: "one", 60),
                ("m2", lambda: "two", 60),
            ]
        )
        assert results == ["one", "two"]

    def test_returns_hot_entries_without_rebuilding(self) -> None:
        cache.cached("m3", lambda: "hot-value", ttl=60)
        calls = []

        def builder() -> str:
            calls.append(1)
            return "unused"

        results = cache.multi_cached_nowait([("m3", builder, 60)])
        assert results == ["hot-value"]
        assert not calls
