import unittest
from dataclasses import dataclass
from datetime import date, datetime

from replay_browser.app import create_app
from replay_browser.config import AppConfig
from replay_browser.db_client import (
    MessageDetail,
    MessageSearchResult,
    MessageSummary,
    ReplayBatchResult,
    ReplayBatchSummary,
    ReplayQueueEntry,
)


@dataclass
class FakeRepository:
    list_result: MessageSearchResult
    detail_result: MessageDetail | None
    last_list_args: tuple[int, int, str, str, date | None, date | None, str, str] | None = None
    filtered_ids: list[int] | None = None
    last_filtered_args: tuple[str, str, date | None, date | None] | None = None
    last_get_by_ids: list[int] | None = None
    last_created_ids: list[int] | None = None
    queue_entries: list[ReplayQueueEntry] | None = None
    batch_summaries: list[ReplayBatchSummary] | None = None
    last_queue_args: tuple[str, str, str, date | None, date | None] | None = None
    last_add_args: tuple[str, list[int]] | None = None
    last_removed_ids: list[int] | None = None
    removed_return: int = 0

    def list_messages(
        self,
        page: int,
        page_size: int,
        query: str,
        destination: str,
        start_date: date | None,
        end_date: date | None,
        sort_by: str,
        sort_dir: str,
    ) -> MessageSearchResult:
        self.last_list_args = (page, page_size, query, destination, start_date, end_date, sort_by, sort_dir)
        return self.list_result

    def get_message(self, message_id: int) -> MessageDetail | None:
        _ = message_id
        return self.detail_result

    def list_filtered_message_ids(
        self,
        query: str,
        destination: str,
        start_date: date | None,
        end_date: date | None,
    ) -> list[int]:
        self.last_filtered_args = (query, destination, start_date, end_date)
        return list(self.filtered_ids or [])

    def get_messages_by_ids(self, message_ids: list[int]) -> list[MessageSummary]:
        self.last_get_by_ids = list(message_ids)
        return list(self.list_result.rows)

    def create_replay_batch(self, message_ids: list[int]) -> ReplayBatchResult:
        self.last_created_ids = list(message_ids)
        return ReplayBatchResult(batch_id="batch-123", inserted_count=len(set(message_ids)))

    def list_replay_queue(
        self,
        batch_filter: str,
        sort_by: str,
        sort_dir: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[ReplayQueueEntry]:
        self.last_queue_args = (batch_filter, sort_by, sort_dir, start_date, end_date)
        return list(self.queue_entries or [])

    def list_replay_batches(self) -> list[ReplayBatchSummary]:
        return list(self.batch_summaries or [])

    def add_messages_to_batch(self, batch_id: str, message_ids: list[int]) -> ReplayBatchResult:
        self.last_add_args = (batch_id, list(message_ids))
        return ReplayBatchResult(batch_id=batch_id, inserted_count=len(set(message_ids)))

    def remove_replay_entries(self, replay_ids: list[int]) -> int:
        self.last_removed_ids = list(replay_ids)
        return self.removed_return


class TestAppRoutes(unittest.TestCase):
    def setUp(self) -> None:
        config = AppConfig(
            sql_server="localhost,1433",
            sql_database="IntegrationHub",
            sql_username="sa",
            sql_password="secret",
            sql_encrypt="No",
            sql_trust_server_certificate="Yes",
            page_size=25,
        )

        summary = MessageSummary(
            id=10,
            received_at=datetime(2026, 1, 1, 12, 0, 0),
            stored_at=datetime(2026, 1, 1, 12, 0, 1),
            correlation_id="corr-1",
            source_system="252",
            processing_component="message_store_service",
            target_system="mpi",
            session_id="session-a",
        )

        detail = MessageDetail(
            id=10,
            received_at=datetime(2026, 1, 1, 12, 0, 0),
            stored_at=datetime(2026, 1, 1, 12, 0, 1),
            correlation_id="corr-1",
            source_system="252",
            processing_component="message_store_service",
            target_system="mpi",
            session_id="session-a",
            raw_payload="MSH|^~\\&|252|252|100|100|20250505232332||ADT^A31^ADT_A05|CTRL-1|P|2.5\rEVN|A31",
            xml_payload="<msg />",
        )

        self.fake_repo = FakeRepository(
            list_result=MessageSearchResult(rows=[summary], total_rows=1),
            detail_result=detail,
        )
        self.app = create_app(config=config, repository=self.fake_repo)
        self.client = self.app.test_client()

    def test_list_messages_route(self) -> None:
        response = self.client.get("/messages")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Message Store", response.data)
        self.assertIn(b"corr-1", response.data)

        self.assertEqual(self.fake_repo.last_list_args, (1, 25, "", "", None, None, "id", "desc"))

    def test_list_messages_route_passes_sorting_params(self) -> None:
        response = self.client.get(
            "/messages?q=252&destination=mpi&start_date=2026-01-01&end_date=2026-01-31&sort_by=received_at&sort_dir=asc&page=2"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.fake_repo.last_list_args,
            (2, 25, "252", "mpi", date(2026, 1, 1), date(2026, 1, 31), "received_at", "asc"),
        )

    def test_list_messages_route_swaps_inverted_date_range(self) -> None:
        response = self.client.get("/messages?start_date=2026-02-10&end_date=2026-01-01")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.fake_repo.last_list_args,
            (1, 25, "", "", date(2026, 1, 1), date(2026, 2, 10), "id", "desc"),
        )

    def test_message_detail_route(self) -> None:
        response = self.client.get("/messages/10")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Structured HL7", response.data)
        self.assertIn(b"ADT^A31^ADT_A05", response.data)
        self.assertIn(b"CTRL-1", response.data)

    def test_message_detail_returns_not_found(self) -> None:
        self.fake_repo.detail_result = None

        response = self.client.get("/messages/999")

        self.assertEqual(response.status_code, 404)

    def test_replay_review_with_selected_ids(self) -> None:
        response = self.client.post(
            "/replay/review",
            data={"mode": "selected", "message_ids": ["10", "12", "bad", "10"]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Review replay batch", response.data)
        # Invalid value ignored, duplicates collapsed, result sorted.
        self.assertEqual(self.fake_repo.last_get_by_ids, [10, 12])

    def test_replay_review_all_filtered_uses_filters(self) -> None:
        self.fake_repo.filtered_ids = [1, 2, 3]

        response = self.client.post(
            "/replay/review",
            data={
                "mode": "all_filtered",
                "q": "252",
                "destination": "mpi",
                "start_date": "2026-01-01",
                "end_date": "2026-01-31",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.fake_repo.last_filtered_args,
            ("252", "mpi", date(2026, 1, 1), date(2026, 1, 31)),
        )
        self.assertEqual(self.fake_repo.last_get_by_ids, [1, 2, 3])

    def test_replay_create_enqueues_batch(self) -> None:
        response = self.client.post(
            "/replay/create",
            data={"message_ids": ["10", "12"]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.fake_repo.last_created_ids, [10, 12])
        self.assertIn(b"batch-123", response.data)
        self.assertIn(b"Replay batch created", response.data)

    def test_replay_create_with_no_ids_does_not_enqueue(self) -> None:
        response = self.client.post("/replay/create", data={})

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.fake_repo.last_created_ids)
        self.assertIn(b"No messages were selected", response.data)

    def test_replay_create_adds_to_existing_batch(self) -> None:
        response = self.client.post(
            "/replay/create",
            data={
                "message_ids": ["10", "12"],
                "action": "add",
                "existing_batch_id": "batch-abc",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.fake_repo.last_created_ids)
        self.assertEqual(self.fake_repo.last_add_args, ("batch-abc", [10, 12]))
        self.assertIn(b"batch-abc", response.data)
        self.assertIn(b"Messages added to batch", response.data)

    def test_replay_create_add_without_batch_id_falls_back_to_new_batch(self) -> None:
        response = self.client.post(
            "/replay/create",
            data={"message_ids": ["10"], "action": "add", "existing_batch_id": "  "},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.fake_repo.last_created_ids, [10])
        self.assertIsNone(self.fake_repo.last_add_args)

    def test_replay_queue_lists_entries(self) -> None:
        self.fake_repo.queue_entries = [
            ReplayQueueEntry(
                replay_id=5,
                batch_id="batch-xyz",
                message_id=10,
                status="Pending",
                created_at=datetime(2026, 1, 2, 9, 0, 0),
                processed_at=None,
                correlation_id="corr-1",
                source_system="252",
                target_system="mpi",
            )
        ]
        self.fake_repo.batch_summaries = [
            ReplayBatchSummary(batch_id="batch-xyz", total=1, pending=1, created_at=datetime(2026, 1, 2, 9, 0, 0)),
        ]

        response = self.client.get("/replay/queue?batch=batch&sort_by=message_id&sort_dir=asc")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.fake_repo.last_queue_args, ("batch", "message_id", "asc", None, None))
        self.assertIn(b"batch-xyz", response.data)
        self.assertIn(b"Pending", response.data)

    def test_replay_queue_defaults_invalid_sort(self) -> None:
        response = self.client.get("/replay/queue?sort_by=bogus&sort_dir=sideways")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.fake_repo.last_queue_args, ("", "created_at", "desc", None, None))

    def test_replay_queue_filters_by_created_date_range(self) -> None:
        response = self.client.get("/replay/queue?start_date=2026-02-10&end_date=2026-01-01")

        self.assertEqual(response.status_code, 200)
        # Inverted range is swapped back into chronological order.
        self.assertEqual(
            self.fake_repo.last_queue_args,
            ("", "created_at", "desc", date(2026, 1, 1), date(2026, 2, 10)),
        )

    def test_replay_queue_remove_deletes_selected(self) -> None:
        self.fake_repo.removed_return = 2

        response = self.client.post(
            "/replay/queue/remove",
            data={"replay_ids": ["5", "7", "bad"], "batch": "batch-xyz", "sort_by": "status", "sort_dir": "asc"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.fake_repo.last_removed_ids, [5, 7])
        self.assertEqual(self.fake_repo.last_queue_args, ("batch-xyz", "status", "asc", None, None))
        self.assertIn(b"Removed", response.data)

    def test_replay_queue_remove_with_no_ids_is_noop(self) -> None:
        response = self.client.post("/replay/queue/remove", data={})

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.fake_repo.last_removed_ids)


if __name__ == "__main__":
    unittest.main()
