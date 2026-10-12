from __future__ import annotations

import unittest

from lookup_service.store.cosmos_store import MAX_BATCH_BYTES, MAX_BATCH_OPERATIONS, _batches


class BatchingTests(unittest.TestCase):
    def test_splits_at_operation_limit(self) -> None:
        operations = [("upsert", ({"id": str(i)},)) for i in range(250)]
        sizes = [len(batch) for batch in _batches(operations)]
        self.assertEqual(sizes, [MAX_BATCH_OPERATIONS, MAX_BATCH_OPERATIONS, 50])

    def test_splits_at_byte_limit(self) -> None:
        big = "x" * (MAX_BATCH_BYTES // 3)
        operations = [("upsert", ({"id": str(i), "v": big},)) for i in range(5)]
        batches = _batches(operations)
        self.assertEqual([len(batch) for batch in batches], [2, 2, 1])

    def test_empty(self) -> None:
        self.assertEqual(_batches([]), [])


if __name__ == "__main__":
    unittest.main()
