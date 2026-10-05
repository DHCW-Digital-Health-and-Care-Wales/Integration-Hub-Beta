from __future__ import annotations

import unittest

from lookup_service.cache.table_cache import TableCache
from tests.helpers import make_row


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class TableCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.cache = TableCache(ttl_seconds=60, max_entries=2, timer=self.clock)

    def test_hit_and_miss_counters(self) -> None:
        self.assertIsNone(self.cache.get(("A",)))
        self.cache.put(("A",), make_row("A", label="x"))
        self.assertIsNotNone(self.cache.get(("A",)))
        self.assertEqual((self.cache.hits, self.cache.misses), (1, 1))

    def test_entries_expire_after_ttl(self) -> None:
        self.cache.put(("A",), make_row("A", label="x"))
        self.clock.now += 59
        self.assertIsNotNone(self.cache.get(("A",)))
        self.clock.now += 2
        self.assertIsNone(self.cache.get(("A",)))
        self.assertEqual(len(self.cache), 0)

    def test_evicts_beyond_max_entries(self) -> None:
        for key in ("A", "B", "C"):
            self.cache.put((key,), make_row(key, label="x"))
        self.assertEqual(len(self.cache), 2)

    def test_clear(self) -> None:
        self.cache.put(("A",), make_row("A", label="x"))
        self.cache.clear()
        self.assertEqual(len(self.cache), 0)


if __name__ == "__main__":
    unittest.main()
