import unittest

from message_replay_job.replay_record import ReplayRecord


class TestReplayRecord(unittest.TestCase):
    def test_replay_record_creation(self) -> None:
        record = ReplayRecord(
            replay_id=1,
            message_id=100,
            raw_payload="MSH|^~\\&|...",
            correlation_id="corr-1",
            session_id="mpi",
        )
        self.assertEqual(record.replay_id, 1)
        self.assertEqual(record.message_id, 100)
        self.assertEqual(record.raw_payload, "MSH|^~\\&|...")
        self.assertEqual(record.correlation_id, "corr-1")
        self.assertEqual(record.session_id, "mpi")


    def test_replay_record_is_frozen(self) -> None:
        record = ReplayRecord(
            replay_id=1,
            message_id=100,
            raw_payload="MSH|^~\\&|...",
            correlation_id="corr-1",
            session_id="mpi",
        )
        with self.assertRaises(AttributeError):
            record.replay_id = 999  # type: ignore[misc]

    def test_replay_record_equality(self) -> None:
        kwargs = dict(replay_id=1, message_id=100, raw_payload="payload", correlation_id="corr", session_id="mpi")
        record_a = ReplayRecord(**kwargs)
        record_b = ReplayRecord(**kwargs)
        self.assertEqual(record_a, record_b)

    def test_replay_record_inequality(self) -> None:
        shared = dict(message_id=100, raw_payload="payload", correlation_id="corr", session_id="mpi")
        record_a = ReplayRecord(replay_id=1, **shared)
        record_b = ReplayRecord(replay_id=2, **shared)
        self.assertNotEqual(record_a, record_b)


if __name__ == "__main__":
    unittest.main()
