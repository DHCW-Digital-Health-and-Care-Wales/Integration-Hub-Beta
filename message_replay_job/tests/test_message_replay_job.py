import unittest
from unittest.mock import MagicMock, call, patch

from azure.servicebus.exceptions import OperationTimeoutError, ServiceBusError

from message_replay_job.message_replay_job import MessageReplayJob
from message_replay_job.replay_record import ReplayRecord
from message_replay_job.replay_status import ReplayStatus


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
    config.replay_batch_size = 100
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
        self.assertEqual(update_calls[0], call([1, 2], ReplayStatus.LOADED))
        self.assertEqual(update_calls[1], call([3], ReplayStatus.LOADED))

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

        mock_db.update_statuses.assert_called_once_with([1], ReplayStatus.LOADED)

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
        mock_db.update_statuses.assert_called_once_with([1], ReplayStatus.LOADED)

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

        mock_db.update_statuses.assert_called_once_with([1], ReplayStatus.LOADED)

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

        mock_db.update_statuses.assert_called_once_with([1], ReplayStatus.FAILED)


class TestMessageReplayJobLoadedUpdateFailure(unittest.TestCase):
    """Tests for failure when marking records as Loaded."""

    @patch("message_replay_job.message_replay_job.ServiceBusClientFactory")
    @patch("message_replay_job.message_replay_job.DatabaseClient")
    def test_run_aborts_on_loaded_update_double_failure(
        self,
        mock_db_client_cls: MagicMock,
        mock_factory_cls: MagicMock,
    ) -> None:
        """update_statuses is retried once, then aborts on the second failure."""
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

        # Retried once: two calls total
        self.assertEqual(mock_db.update_statuses.call_count, 2)
        for c in mock_db.update_statuses.call_args_list:
            self.assertEqual(c, call([1], ReplayStatus.LOADED))

    @patch("message_replay_job.message_replay_job.ServiceBusClientFactory")
    @patch("message_replay_job.message_replay_job.DatabaseClient")
    def test_run_succeeds_when_loaded_update_recovers_on_retry(
        self,
        mock_db_client_cls: MagicMock,
        mock_factory_cls: MagicMock,
    ) -> None:
        """First update_statuses call fails, retry succeeds — job continues."""
        config = _make_config()
        mock_db = MagicMock()
        mock_db_client_cls.return_value = mock_db
        mock_db.fetch_batch.side_effect = [[_make_record(1, 100)], []]
        mock_db.update_statuses.side_effect = [Exception("DB transient"), None]

        mock_sender_client = MagicMock()
        mock_factory = MagicMock()
        mock_factory.create_queue_sender_client.return_value = mock_sender_client
        mock_factory_cls.return_value = mock_factory

        job = MessageReplayJob(config)
        job.run()

        self.assertEqual(mock_db.update_statuses.call_count, 2)
        for c in mock_db.update_statuses.call_args_list:
            self.assertEqual(c, call([1], ReplayStatus.LOADED))


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
        self.assertEqual(props_0["CorrelationId"], "corr-1")
        self.assertEqual(props_0["ReplayId"], "1")
        self.assertEqual(props_0["MessageId"], "100")
        self.assertEqual(props_1["CorrelationId"], "corr-2")
        self.assertEqual(props_1["ReplayId"], "2")
        self.assertEqual(props_1["MessageId"], "200")

    def test_build_messages_returns_empty_for_no_records(self) -> None:
        messages = MessageReplayJob._build_messages([])
        self.assertEqual(messages, [])


class TestMessageReplayJobOversizedMessage(unittest.TestCase):
    """Tests for the oversized-message (unrecoverable ValueError) scenario."""

    @patch("message_replay_job.message_replay_job.ServiceBusClientFactory")
    @patch("message_replay_job.message_replay_job.DatabaseClient")
    def test_run_aborts_without_retry_on_oversized_message_error(
        self,
        mock_db_client_cls: MagicMock,
        mock_factory_cls: MagicMock,
    ) -> None:
        """A ValueError from send_message_batch (single message too large) must:
        - NOT be retried (send_message_batch called once)
        - mark the batch as 'Failed' before re-raising
        - cause the job to abort
        """
        config = _make_config()
        mock_db = MagicMock()
        mock_db_client_cls.return_value = mock_db
        mock_db.fetch_batch.return_value = [_make_record(1, 100)]

        mock_sender_client = MagicMock()
        mock_sender_client.send_message_batch.side_effect = ValueError(
            "Single message exceeds Service Bus max message size"
        )
        mock_factory = MagicMock()
        mock_factory.create_queue_sender_client.return_value = mock_sender_client
        mock_factory_cls.return_value = mock_factory

        job = MessageReplayJob(config)
        with self.assertRaises(ValueError):
            job.run()

        # NOT retried — only one send attempt
        self.assertEqual(mock_sender_client.send_message_batch.call_count, 1)
        # Batch marked Failed before aborting
        mock_db.update_statuses.assert_called_once_with([1], ReplayStatus.FAILED)


class TestMessageReplayJobOperationTimeout(unittest.TestCase):
    """Tests for OperationTimeoutError handling during send."""

    @patch("message_replay_job.message_replay_job.ServiceBusClientFactory")
    @patch("message_replay_job.message_replay_job.DatabaseClient")
    def test_send_retries_on_operation_timeout_and_succeeds(
        self,
        mock_db_client_cls: MagicMock,
        mock_factory_cls: MagicMock,
    ) -> None:
        """OperationTimeoutError on first send, retry succeeds — batch marked Loaded."""
        config = _make_config()
        mock_db = MagicMock()
        mock_db_client_cls.return_value = mock_db
        mock_db.fetch_batch.side_effect = [[_make_record(1, 100)], []]

        mock_sender_client = MagicMock()
        mock_sender_client.send_message_batch.side_effect = [
            OperationTimeoutError(message="Send timed out"),
            None,
        ]
        mock_factory = MagicMock()
        mock_factory.create_queue_sender_client.return_value = mock_sender_client
        mock_factory_cls.return_value = mock_factory

        job = MessageReplayJob(config)
        job.run()

        self.assertEqual(mock_sender_client.send_message_batch.call_count, 2)
        mock_db.update_statuses.assert_called_once_with([1], ReplayStatus.LOADED)

    @patch("message_replay_job.message_replay_job.ServiceBusClientFactory")
    @patch("message_replay_job.message_replay_job.DatabaseClient")
    def test_send_marks_failed_on_operation_timeout_double_failure(
        self,
        mock_db_client_cls: MagicMock,
        mock_factory_cls: MagicMock,
    ) -> None:
        """OperationTimeoutError on both attempts — batch marked Failed."""
        config = _make_config()
        mock_db = MagicMock()
        mock_db_client_cls.return_value = mock_db
        mock_db.fetch_batch.return_value = [_make_record(1, 100)]

        mock_sender_client = MagicMock()
        mock_sender_client.send_message_batch.side_effect = OperationTimeoutError(message="Send timed out")
        mock_factory = MagicMock()
        mock_factory.create_queue_sender_client.return_value = mock_sender_client
        mock_factory_cls.return_value = mock_factory

        job = MessageReplayJob(config)
        with self.assertRaises(OperationTimeoutError):
            job.run()

        self.assertEqual(mock_sender_client.send_message_batch.call_count, 2)
        mock_db.update_statuses.assert_called_once_with([1], ReplayStatus.FAILED)


class TestMessageReplayJobServiceBusError(unittest.TestCase):
    """Tests for generic ServiceBusError handling during send."""

    @patch("message_replay_job.message_replay_job.ServiceBusClientFactory")
    @patch("message_replay_job.message_replay_job.DatabaseClient")
    def test_send_retries_on_service_bus_error_and_succeeds(
        self,
        mock_db_client_cls: MagicMock,
        mock_factory_cls: MagicMock,
    ) -> None:
        """ServiceBusError on first send, retry succeeds — batch marked Loaded."""
        config = _make_config()
        mock_db = MagicMock()
        mock_db_client_cls.return_value = mock_db
        mock_db.fetch_batch.side_effect = [[_make_record(1, 100)], []]

        mock_sender_client = MagicMock()
        mock_sender_client.send_message_batch.side_effect = [
            ServiceBusError("Transient SB error"),
            None,
        ]
        mock_factory = MagicMock()
        mock_factory.create_queue_sender_client.return_value = mock_sender_client
        mock_factory_cls.return_value = mock_factory

        job = MessageReplayJob(config)
        job.run()

        self.assertEqual(mock_sender_client.send_message_batch.call_count, 2)
        mock_db.update_statuses.assert_called_once_with([1], ReplayStatus.LOADED)

    @patch("message_replay_job.message_replay_job.ServiceBusClientFactory")
    @patch("message_replay_job.message_replay_job.DatabaseClient")
    def test_send_marks_failed_on_service_bus_error_double_failure(
        self,
        mock_db_client_cls: MagicMock,
        mock_factory_cls: MagicMock,
    ) -> None:
        """ServiceBusError on both attempts — batch marked Failed."""
        config = _make_config()
        mock_db = MagicMock()
        mock_db_client_cls.return_value = mock_db
        mock_db.fetch_batch.return_value = [_make_record(1, 100)]

        mock_sender_client = MagicMock()
        mock_sender_client.send_message_batch.side_effect = ServiceBusError("Persistent SB error")
        mock_factory = MagicMock()
        mock_factory.create_queue_sender_client.return_value = mock_sender_client
        mock_factory_cls.return_value = mock_factory

        job = MessageReplayJob(config)
        with self.assertRaises(ServiceBusError):
            job.run()

        self.assertEqual(mock_sender_client.send_message_batch.call_count, 2)
        mock_db.update_statuses.assert_called_once_with([1], ReplayStatus.FAILED)


class TestRetryOnce(unittest.TestCase):
    """Tests for the _retry_once helper method."""

    def _make_job(self) -> MessageReplayJob:
        return MessageReplayJob(_make_config())

    @patch("message_replay_job.message_replay_job.DatabaseClient")
    def test_retry_once_returns_value_on_first_success(self, _mock_db_cls: MagicMock) -> None:
        job = self._make_job()
        result = job._retry_once(lambda: 42, "test-op")
        self.assertEqual(result, 42)

    @patch("message_replay_job.message_replay_job.DatabaseClient")
    def test_retry_once_retries_and_returns_on_second_success(self, _mock_db_cls: MagicMock) -> None:
        job = self._make_job()
        op = MagicMock(side_effect=[Exception("transient"), "ok"])
        result = job._retry_once(op, "test-op")
        self.assertEqual(result, "ok")
        self.assertEqual(op.call_count, 2)

    @patch("message_replay_job.message_replay_job.DatabaseClient")
    def test_retry_once_raises_on_double_failure(self, _mock_db_cls: MagicMock) -> None:
        job = self._make_job()
        op = MagicMock(side_effect=Exception("permanent"))
        with self.assertRaises(Exception) as ctx:
            job._retry_once(op, "test-op")
        self.assertIn("permanent", str(ctx.exception))
        self.assertEqual(op.call_count, 2)


if __name__ == "__main__":
    unittest.main()
