import unittest
from unittest.mock import MagicMock, call, patch

from azure.servicebus.exceptions import MessageSizeExceededError

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
    config.sql_password = "secret"
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

        mock_sender = MagicMock()
        mock_batch = MagicMock()
        mock_sender.create_message_batch.return_value = mock_batch
        mock_factory = MagicMock()
        mock_factory.servicebus_client.get_queue_sender.return_value = mock_sender
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

        mock_sender = MagicMock()
        mock_sender.create_message_batch.return_value = MagicMock()
        mock_factory = MagicMock()
        mock_factory.servicebus_client.get_queue_sender.return_value = mock_sender
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

        mock_sender = MagicMock()
        mock_factory = MagicMock()
        mock_factory.servicebus_client.get_queue_sender.return_value = mock_sender
        mock_factory_cls.return_value = mock_factory

        job = MessageReplayJob(config)
        job.run()

        mock_db.update_statuses.assert_not_called()
        mock_sender.send_messages.assert_not_called()


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

        mock_sender = MagicMock()
        mock_sender.create_message_batch.return_value = MagicMock()
        mock_factory = MagicMock()
        mock_factory.servicebus_client.get_queue_sender.return_value = mock_sender
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

        mock_sender = MagicMock()
        mock_factory = MagicMock()
        mock_factory.servicebus_client.get_queue_sender.return_value = mock_sender
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

        mock_sender = MagicMock()
        # First create_message_batch call raises on send, second succeeds
        mock_batch_fail = MagicMock()
        mock_batch_success = MagicMock()
        mock_sender.create_message_batch.side_effect = [mock_batch_fail, mock_batch_success]
        mock_sender.send_messages.side_effect = [Exception("SB error"), None]
        mock_factory = MagicMock()
        mock_factory.servicebus_client.get_queue_sender.return_value = mock_sender
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

        mock_sender = MagicMock()
        mock_sender.create_message_batch.return_value = MagicMock()
        mock_sender.send_messages.side_effect = Exception("SB error")
        mock_factory = MagicMock()
        mock_factory.servicebus_client.get_queue_sender.return_value = mock_sender
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

        mock_sender = MagicMock()
        mock_sender.create_message_batch.return_value = MagicMock()
        mock_factory = MagicMock()
        mock_factory.servicebus_client.get_queue_sender.return_value = mock_sender
        mock_factory_cls.return_value = mock_factory

        job = MessageReplayJob(config)
        with self.assertRaises(Exception):
            job.run()

        mock_db.update_statuses.assert_called_once_with([1], "Loaded")


class TestSendBatchToServiceBus(unittest.TestCase):
    """Tests for the _send_batch_to_service_bus auto-split logic."""

    def _make_job(self) -> MessageReplayJob:
        config = _make_config()
        with patch("message_replay_job.message_replay_job.DatabaseClient"):
            return MessageReplayJob(config)

    def test_send_batch_sends_all_messages_in_single_batch(self) -> None:
        job = self._make_job()
        mock_sender = MagicMock()
        mock_batch = MagicMock()
        mock_sender.create_message_batch.return_value = mock_batch

        records = [_make_record(i, i * 100) for i in range(3)]
        job._send_batch_to_service_bus(mock_sender, records)

        self.assertEqual(mock_batch.add_message.call_count, 3)
        mock_sender.send_messages.assert_called_once_with(mock_batch)

    def test_send_batch_creates_new_sb_batch_when_full(self) -> None:
        """When add_message raises MessageSizeExceededError, flush and start new batch."""
        job = self._make_job()
        mock_sender = MagicMock()

        # First batch accepts 2 messages, rejects the 3rd
        mock_batch_1 = MagicMock()
        add_call_count = 0

        def add_message_side_effect(msg: MagicMock) -> None:
            nonlocal add_call_count
            add_call_count += 1
            if add_call_count == 3:
                raise MessageSizeExceededError("Batch full")

        mock_batch_1.add_message.side_effect = add_message_side_effect

        mock_batch_2 = MagicMock()
        mock_sender.create_message_batch.side_effect = [mock_batch_1, mock_batch_2]

        records = [_make_record(i, i * 100) for i in range(3)]
        job._send_batch_to_service_bus(mock_sender, records)

        # First batch flushed, then second batch with the 3rd message
        send_calls = mock_sender.send_messages.call_args_list
        self.assertEqual(len(send_calls), 2)
        self.assertEqual(send_calls[0], call(mock_batch_1))
        self.assertEqual(send_calls[1], call(mock_batch_2))

    def test_send_batch_raises_when_single_message_too_large(self) -> None:
        """When a single message exceeds max size on an empty batch, raise ValueError."""
        job = self._make_job()
        mock_sender = MagicMock()
        mock_batch = MagicMock()
        mock_batch.add_message.side_effect = MessageSizeExceededError("Too large")
        mock_sender.create_message_batch.return_value = mock_batch

        records = [_make_record(1, 100)]
        with self.assertRaises(ValueError) as ctx:
            job._send_batch_to_service_bus(mock_sender, records)

        self.assertIn("ReplayId=1", str(ctx.exception))
        self.assertIn("exceeds Service Bus max message size", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
