import unittest

from message_replay_job.replay_record import ReplayRecord


class TestReplayRecord(unittest.TestCase):
    def test_replay_record_creation(self) -> None:
        record = ReplayRecord(
            replay_id=1,
            message_id=100,
            raw_payload="MSH|^~\\&|...",
            correlation_id="corr-1",
        )
        self.assertEqual(record.replay_id, 1)
        self.assertEqual(record.message_id, 100)
        self.assertEqual(record.raw_payload, "MSH|^~\\&|...")
        self.assertEqual(record.correlation_id, "corr-1")

    def test_replay_record_is_frozen(self) -> None:
        record = ReplayRecord(
            replay_id=1,
            message_id=100,
            raw_payload="MSH|^~\\&|...",
            correlation_id="corr-1",
        )
        with self.assertRaises(AttributeError):
            record.replay_id = 999  # type: ignore[misc]

    def test_replay_record_equality(self) -> None:
        record_a = ReplayRecord(replay_id=1, message_id=100, raw_payload="payload", correlation_id="corr")
        record_b = ReplayRecord(replay_id=1, message_id=100, raw_payload="payload", correlation_id="corr")
        self.assertEqual(record_a, record_b)

    def test_replay_record_inequality(self) -> None:
        record_a = ReplayRecord(replay_id=1, message_id=100, raw_payload="payload", correlation_id="corr")
        record_b = ReplayRecord(replay_id=2, message_id=100, raw_payload="payload", correlation_id="corr")
        self.assertNotEqual(record_a, record_b)


if __name__ == "__main__":
    unittest.main()
