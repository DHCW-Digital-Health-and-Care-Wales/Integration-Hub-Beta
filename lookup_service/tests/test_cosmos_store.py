"""Opt-in integration tests against a real Cosmos DB (the local emulator).

Skipped unless LOOKUP_IT_COSMOS_ENDPOINT is set, e.g.:

    LOOKUP_IT_COSMOS_ENDPOINT=https://localhost:8081 \
    LOOKUP_IT_COSMOS_KEY=<emulator key> \
    uv run python -m unittest tests.test_cosmos_store

Each run uses a throwaway database that is deleted afterwards.
"""

from __future__ import annotations

import os
import unittest
import uuid

from azure.cosmos.aio import CosmosClient

from lookup_service.models import UploadInfo
from lookup_service.store.cosmos_store import CosmosTableStore
from tests.helpers import codes_definition, make_row, make_settings

ENDPOINT = os.getenv("LOOKUP_IT_COSMOS_ENDPOINT")
KEY = os.getenv("LOOKUP_IT_COSMOS_KEY")


@unittest.skipUnless(ENDPOINT and KEY, "set LOOKUP_IT_COSMOS_ENDPOINT and LOOKUP_IT_COSMOS_KEY to run")
class CosmosTableStoreIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.database = f"lookup-it-{uuid.uuid4().hex[:8]}"
        self.settings = make_settings(cosmos_endpoint=ENDPOINT, cosmos_key=KEY, cosmos_database=self.database,
                                      cosmos_disable_ssl_verify=True, upload_concurrency=8)
        self.settings.validate()
        self.store = CosmosTableStore(self.settings)
        await self.store.open()

    async def asyncTearDown(self) -> None:
        await self.store.close()
        async with CosmosClient(ENDPOINT or "", credential=KEY or "", connection_verify=False,
                                enable_endpoint_discovery=False) as client:
            await client.delete_database(self.database)

    async def test_replace_then_read(self) -> None:
        definition = codes_definition(key_columns=("fac", "code"), value_columns=("label",))
        rows = [make_row("F1", "A/1", label="slash"), make_row("F1", "B:2", label="colon"),
                make_row("F2", "x" * 300, label="long")]
        result = await self.store.replace_table(definition, rows, UploadInfo("tester", "codes.csv"))
        self.assertEqual((result.upserted, result.removed), (3, 0))

        row = await self.store.get_row("codes", ("F1", "A/1"))
        self.assertIsNotNone(row)
        self.assertEqual(row.values["label"] if row else None, "slash")
        long_row = await self.store.get_row("codes", ("F2", "x" * 300))
        self.assertEqual(long_row.values["label"] if long_row else None, "long")
        self.assertIsNone(await self.store.get_row("codes", ("F9", "nope")))
        self.assertIsNone(await self.store.get_row("other_table", ("F1", "A/1")))

        record = await self.store.get_table("codes")
        self.assertIsNotNone(record)
        if record:
            self.assertEqual(record.definition, definition)
            self.assertEqual((record.stats.row_count, record.stats.last_upload_by), (3, "tester"))
        self.assertEqual([r.definition.name for r in await self.store.list_tables()], ["codes"])
        self.assertEqual(len(await self.store.load_rows("codes")), 3)

    async def test_replace_removes_stale_rows(self) -> None:
        definition = codes_definition()
        await self.store.replace_table(definition, [make_row("A", label="1"), make_row("B", label="2")],
                                       UploadInfo("t", None))
        result = await self.store.replace_table(definition, [make_row("B", label="22"), make_row("C", label="3")],
                                                UploadInfo("t", None))
        self.assertEqual((result.upserted, result.removed), (2, 1))
        self.assertIsNone(await self.store.get_row("codes", ("A",)))
        row = await self.store.get_row("codes", ("B",))
        self.assertEqual(row.values["label"] if row else None, "22")

    async def test_query_rows_search_and_paging(self) -> None:
        rows = [make_row(f"K{i:02d}", label=str(i)) for i in range(25)] + [make_row("ZZ", label="z")]
        await self.store.replace_table(codes_definition(), rows, UploadInfo("t", None))
        page, total = await self.store.query_rows("codes", None, 10, 5)
        self.assertEqual(total, 26)
        self.assertEqual([r.key for r in page], [(f"K{i:02d}",) for i in range(10, 15)])
        page, total = await self.store.query_rows("codes", "zz", 0, 10)
        self.assertEqual((total, [r.key for r in page]), (1, [("ZZ",)]))


if __name__ == "__main__":
    unittest.main()
