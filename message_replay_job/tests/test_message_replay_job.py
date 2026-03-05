import unittest
from unittest.mock import MagicMock, call, patch

from message_replay_job.message_replay_job import MessageReplayJob
from message_replay_job.replay_record import ReplayRecord


def _make_record(replay_id: int = 1, message_id: int = 100) -> ReplayRecord:
    """Helper to create a ReplayRecord with sensible defaults."""
    return ReplayRecord(
        replay_id=replay_id,
        message_id=message_id,
        raw_payload=f"MSH|^~\\&|payload-{replay_id}",
        correlation_id=f"corr-{replay_id}",
    )


def _make_config() -> MagicMock:
    """Create a mock AppConfig with all fields populated."""
    config = MagicMock()
    config.replay_batch_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    config.connection_string = "conn_str"
    config.service_bus_namespace = None
    config.priority_queue_name = "priority-queue"
    config.sql_server = "localhost,1433"
    config.sql_database = "IntegrationHub"
    config.sql_username = "sa"
    config.sql_password = "secret"  # nosec B105 — test fixture, not real password
    config.sql_encrypt = "yes"
    config.sql_trust_server_certificate = "yes"
    config.managed_identity_client_id = None
    return config


class TestMessageReplayJobRun(unittest.TestCase):
    """Tests for the main run() loop of MessageReplayJob."""

    @patch("message_replay_job.message_replay_job.ServiceBusClientFactory")
    @patch("message_replay_job.message_replay_job.DatabaseClient")
    def test_run_processes_all_batches_until_empty(
        self,
        mock_db_client_cls: MagicMock,
        mock_factory_cls: MagicMock,
    ) -> None:
        """Two non-empty batches followed by an empty one -> two Loaded updates."""
        config = _make_config()
        mock_db = MagicMock()
        mock_db_client_cls.return_value = mock_db

        batch_1 = [_make_record(1, 100), _make_record(2, 200)]
        batch_2 = [_make_record(3, 300)]
        mock_db.fetch_batch.side_effect = [batch_1, batch_2, []]

        mock_sender_client = MagicMock()
        mock_factory = MagicMock()
        mock_factory.create_queue_sender_client.return_value = mock_sender_client
        mock_factory_cls.return_value = mock_factory

        job = MessageReplayJob(config)
        job.run()

        self.assertEqual(mock_db.fetch_batch.call_count, 3)
        update_calls = mock_db.update_statuses.call_args_list
        self.assertEqual(len(update_calls), 2)
        self.assertEqual(update_calls[0], call([1, 2], "Loaded"))
        self.assertEqual(update_calls[1], call([3], "Loaded"))

    @patch("message_replay_job.message_replay_job.ServiceBusClientFactory")
    @patch("message_replay_job.message_replay_job.DatabaseClient")
    def test_run_single_batch_then_done(
        self,
        mock_db_client_cls: MagicMock,
        mock_factory_cls: MagicMock,
    ) -> None:
        config = _make_config()
        mock_db = MagicMock()
        mock_db_client_cls.return_value = mock_db
        mock_db.fetch_batch.side_effect = [[_make_record(1, 100)], []]

        mock_sender_client = MagicMock()
        mock_factory = MagicMock()
        mock_factory.create_queue_sender_client.return_value = mock_sender_client
        mock_factory_cls.return_value = mock_factory

        job = MessageReplayJob(config)
        job.run()

        mock_db.update_statuses.assert_called_once_with([1], "Loaded")

    @patch("message_replay_job.message_replay_job.ServiceBusClientFactory")
    @patch("message_replay_job.message_replay_job.DatabaseClient")
    def test_run_exits_immediately_when_no_pending_records(
        self,
        mock_db_client_cls: MagicMock,
        mock_factory_cls: MagicMock,
    ) -> None:
        config = _make_config()
        mock_db = MagicMock()
        mock_db_client_cls.return_value = mock_db
        mock_db.fetch_batch.return_value = []

        mock_sender_client = MagicMock()
        mock_factory = MagicMock()
        mock_factory.create_queue_sender_client.return_value = mock_sender_client
        mock_factory_cls.return_value = mock_factory

        job = MessageReplayJob(config)
        job.run()

        mock_db.update_statuses.assert_not_called()
        mock_sender_client.send_message_batch.assert_not_called()

    @patch("message_replay_job.message_replay_job.ServiceBusClientFactory")
    @patch("message_replay_job.message_replay_job.DatabaseClient")
    def test_run_calls_send_message_batch_with_built_messages(
        self,
        mock_db_client_cls: MagicMock,
        mock_factory_cls: MagicMock,
    ) -> None:
        """Verify the job builds ServiceBusMessages and delegates to send_message_batch."""
        config = _make_config()
        mock_db = MagicMock()
        mock_db_client_cls.return_value = mock_db
        mock_db.fetch_batch.side_effect = [[_make_record(1, 100)], []]

        mock_sender_client = MagicMock()
        mock_factory = MagicMock()
        mock_factory.create_queue_sender_client.return_value = mock_sender_client
        mock_factory_cls.return_value = mock_factory

        job = MessageReplayJob(config)
        job.run()

        mock_sender_client.send_message_batch.assert_called_once()
        messages = mock_sender_client.send_message_batch.call_args[0][0]
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].application_properties["CorrelationId"], "corr-1")
        self.assertEqual(messages[0].application_properties["ReplayId"], "1")
        self.assertEqual(messages[0].application_properties["MessageId"], "100")


class TestMessageReplayJobFetchRetry(unittest.TestCase):
    """Tests for fetch retry logic."""

    @patch("message_replay_job.message_replay_job.ServiceBusClientFactory")
    @patch("message_replay_job.message_replay_job.DatabaseClient")
    def test_run_retries_fetch_on_first_failure(
        self,
        mock_db_client_cls: MagicMock,
        mock_factory_cls: MagicMock,
    ) -> None:
        config = _make_config()
        mock_db = MagicMock()
        mock_db_client_cls.return_value = mock_db

        records = [_make_record(1, 100)]
        mock_db.fetch_batch.side_effect = [Exception("DB error"), records, []]

        mock_sender_client = MagicMock()
        mock_factory = MagicMock()
        mock_factory.create_queue_sender_client.return_value = mock_sender_client
        mock_factory_cls.return_value = mock_factory

        job = MessageReplayJob(config)
        job.run()

        self.assertEqual(mock_db.fetch_batch.call_count, 3)
        mock_db.update_statuses.assert_called_once_with([1], "Loaded")

    @patch("message_replay_job.message_replay_job.ServiceBusClientFactory")
    @patch("message_replay_job.message_replay_job.DatabaseClient")
    def test_run_aborts_on_fetch_double_failure(
        self,
        mock_db_client_cls: MagicMock,
        mock_factory_cls: MagicMock,
    ) -> None:
        config = _make_config()
        mock_db = MagicMock()
        mock_db_client_cls.return_value = mock_db
        mock_db.fetch_batch.side_effect = Exception("DB error")

        mock_sender_client = MagicMock()
        mock_factory = MagicMock()
        mock_factory.create_queue_sender_client.return_value = mock_sender_client
        mock_factory_cls.return_value = mock_factory

        job = MessageReplayJob(config)
        with self.assertRaises(Exception):
            job.run()

        mock_db.update_statuses.assert_not_called()


class TestMessageReplayJobSendRetry(unittest.TestCase):
    """Tests for service bus send retry logic."""

    @patch("message_replay_job.message_replay_job.ServiceBusClientFactory")
    @patch("message_replay_job.message_replay_job.DatabaseClient")
    def test_run_retries_send_on_first_failure(
        self,
        mock_db_client_cls: MagicMock,
        mock_factory_cls: MagicMock,
    ) -> None:
        config = _make_config()
        mock_db = MagicMock()
        mock_db_client_cls.return_value = mock_db
        mock_db.fetch_batch.side_effect = [[_make_record(1, 100)], []]

        mock_sender_client = MagicMock()
        mock_sender_client.send_message_batch.side_effect = [Exception("SB error"), None]
        mock_factory = MagicMock()
        mock_factory.create_queue_sender_client.return_value = mock_sender_client
        mock_factory_cls.return_value = mock_factory

        job = MessageReplayJob(config)
        job.run()

        mock_db.update_statuses.assert_called_once_with([1], "Loaded")

    @patch("message_replay_job.message_replay_job.ServiceBusClientFactory")
    @patch("message_replay_job.message_replay_job.DatabaseClient")
    def test_run_marks_failed_and_aborts_on_send_double_failure(
        self,
        mock_db_client_cls: MagicMock,
        mock_factory_cls: MagicMock,
    ) -> None:
        config = _make_config()
        mock_db = MagicMock()
        mock_db_client_cls.return_value = mock_db
        mock_db.fetch_batch.side_effect = [[_make_record(1, 100)]]

        mock_sender_client = MagicMock()
        mock_sender_client.send_message_batch.side_effect = Exception("SB error")
        mock_factory = MagicMock()
        mock_factory.create_queue_sender_client.return_value = mock_sender_client
        mock_factory_cls.return_value = mock_factory

        job = MessageReplayJob(config)
        with self.assertRaises(Exception):
            job.run()

        mock_db.update_statuses.assert_called_once_with([1], "Failed")


class TestMessageReplayJobLoadedUpdateFailure(unittest.TestCase):
    """Tests for failure when marking records as Loaded."""

    @patch("message_replay_job.message_replay_job.ServiceBusClientFactory")
    @patch("message_replay_job.message_replay_job.DatabaseClient")
    def test_run_aborts_immediately_on_loaded_update_failure(
        self,
        mock_db_client_cls: MagicMock,
        mock_factory_cls: MagicMock,
    ) -> None:
        config = _make_config()
        mock_db = MagicMock()
        mock_db_client_cls.return_value = mock_db
        mock_db.fetch_batch.return_value = [_make_record(1, 100)]
        mock_db.update_statuses.side_effect = Exception("DB update error")

        mock_sender_client = MagicMock()
        mock_factory = MagicMock()
        mock_factory.create_queue_sender_client.return_value = mock_sender_client
        mock_factory_cls.return_value = mock_factory

        job = MessageReplayJob(config)
        with self.assertRaises(Exception):
            job.run()

        mock_db.update_statuses.assert_called_once_with([1], "Loaded")


class TestBuildMessages(unittest.TestCase):
    """Tests for the _build_messages static method."""

    def test_build_messages_sets_correct_body_and_properties(self) -> None:
        records = [_make_record(1, 100), _make_record(2, 200)]
        messages = MessageReplayJob._build_messages(records)

        self.assertEqual(len(messages), 2)
        props_0 = messages[0].application_properties
        props_1 = messages[1].application_properties
        self.assertIsNotNone(props_0)
        self.assertIsNotNone(props_1)
        assert props_0 is not None
        assert props_1 is not None
        self.assertEqual(props_0["CorrelationId"], "corr-1")
        self.assertEqual(props_0["ReplayId"], "1")
        self.assertEqual(props_0["MessageId"], "100")
        self.assertEqual(props_1["CorrelationId"], "corr-2")
        self.assertEqual(props_1["ReplayId"], "2")
        self.assertEqual(props_1["MessageId"], "200")

    def test_build_messages_returns_empty_for_no_records(self) -> None:
        messages = MessageReplayJob._build_messages([])
        self.assertEqual(messages, [])


if __name__ == "__main__":
    unittest.main()
