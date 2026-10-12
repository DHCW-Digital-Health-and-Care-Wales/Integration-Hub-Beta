from __future__ import annotations

import asyncio
import unittest

from lookup_service.errors import BackendUnavailableError, KeyNotFoundError, TableNotFoundError
from lookup_service.models import UploadInfo
from lookup_service.resolver import LookupResolver
from tests.helpers import MemoryTableStore, codes_definition, make_row
from tests.test_table_cache import FakeClock


class ResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = MemoryTableStore()
        self.store.put_table(codes_definition(), [make_row("A", label="Alpha")])
        self.store.put_table(codes_definition(name="hot", preload=True), [make_row("H", label="Hot")])
        self.clock = FakeClock()
        self.resolver = LookupResolver(self.store, default_ttl_seconds=300, max_entries=100, timer=self.clock)
        asyncio.run(self.resolver.start())

    def test_ttl_table_reads_store_once_then_serves_from_cache(self) -> None:
        first = asyncio.run(self.resolver.lookup("codes", ["A"]))
        second = asyncio.run(self.resolver.lookup("codes", ["A"]))
        self.assertFalse(first.cached)
        self.assertTrue(second.cached)
        self.assertEqual(second.value, "Alpha")
        self.assertEqual(self.store.get_row_calls, 1)

    def test_cache_entry_expires_after_table_ttl(self) -> None:
        asyncio.run(self.resolver.lookup("codes", ["A"]))
        self.clock.now += 301
        asyncio.run(self.resolver.lookup("codes", ["A"]))
        self.assertEqual(self.store.get_row_calls, 2)

    def test_per_table_ttl_overrides_default(self) -> None:
        self.store.put_table(codes_definition(ttl_seconds=10), [make_row("A", label="Alpha")])
        asyncio.run(self.resolver.refresh_table("codes"))
        asyncio.run(self.resolver.lookup("codes", ["A"]))
        self.clock.now += 11
        asyncio.run(self.resolver.lookup("codes", ["A"]))
        self.assertEqual(self.store.get_row_calls, 2)
        self.assertEqual(self.resolver.detail("codes").ttl_seconds, 10)

    def test_preloaded_table_never_reads_store_per_key(self) -> None:
        result = asyncio.run(self.resolver.lookup("hot", ["H"]))
        self.assertTrue(result.cached)
        self.assertEqual(self.store.get_row_calls, 0)
        with self.assertRaises(KeyNotFoundError):
            asyncio.run(self.resolver.lookup("hot", ["missing"]))
        self.assertEqual(self.store.get_row_calls, 0)

    def test_misses_are_not_cached_yet(self) -> None:
        for _ in range(2):
            with self.assertRaises(KeyNotFoundError):
                asyncio.run(self.resolver.lookup("codes", ["nope"]))
        self.assertEqual(self.store.get_row_calls, 2)

    def test_unknown_table(self) -> None:
        with self.assertRaises(TableNotFoundError):
            asyncio.run(self.resolver.lookup("ghost", ["A"]))

    def test_backend_failure_propagates(self) -> None:
        self.store.fail_reads = True
        with self.assertRaises(BackendUnavailableError):
            asyncio.run(self.resolver.lookup("codes", ["A"]))

    def test_refresh_swaps_preloaded_snapshot_and_drops_cache(self) -> None:
        asyncio.run(self.resolver.lookup("codes", ["A"]))
        asyncio.run(self.store.replace_table(codes_definition(name="hot", preload=True),
                                             [make_row("H", label="Hotter")], UploadInfo("me", None)))
        asyncio.run(self.resolver.refresh_table("hot"))
        self.assertEqual(asyncio.run(self.resolver.lookup("hot", ["H"])).value, "Hotter")

        asyncio.run(self.store.replace_table(codes_definition(), [make_row("A", label="Changed")],
                                             UploadInfo("me", None)))
        asyncio.run(self.resolver.refresh_table("codes"))
        self.assertEqual(asyncio.run(self.resolver.lookup("codes", ["A"])).value, "Changed")

    def test_refresh_of_deleted_table_removes_it(self) -> None:
        del self.store.records["codes"]
        asyncio.run(self.resolver.refresh_table("codes"))
        self.assertFalse(self.resolver.has_table("codes"))

    def test_summaries_report_cache_stats(self) -> None:
        asyncio.run(self.resolver.lookup("codes", ["A"]))
        asyncio.run(self.resolver.lookup("codes", ["A"]))
        summaries = {s.name: s for s in self.resolver.summaries()}
        self.assertEqual(summaries["codes"].cache.mode, "ttl")
        self.assertEqual((summaries["codes"].cache.hits, summaries["codes"].cache.misses), (1, 1))
        self.assertEqual(summaries["codes"].cache.entries, 1)
        self.assertEqual(summaries["hot"].cache.mode, "preloaded")
        self.assertEqual(summaries["hot"].cache.entries, 1)


if __name__ == "__main__":
    unittest.main()
