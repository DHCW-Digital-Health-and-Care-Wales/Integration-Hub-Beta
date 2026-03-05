import unittest
from unittest.mock import MagicMock, patch

from message_replay_job.db_client import DatabaseClient
from message_replay_job.replay_record import ReplayRecord


class TestDatabaseClient(unittest.TestCase):
    """Tests for DatabaseClient with mocked pyodbc."""

    def setUp(self) -> None:
        self.client = DatabaseClient(  # nosec B106 — test fixture, not real credentials
            sql_server="localhost,1433",
            sql_database="IntegrationHub",
            sql_username="sa",
            sql_password="secret",
            sql_encrypt="yes",
            sql_trust_server_certificate="yes",
        )

    def tearDown(self) -> None:
        self.client.close()

    # ------------------------------------------------------------------
    # fetch_batch — happy path
    # ------------------------------------------------------------------

    @patch("message_replay_job.db_client.pyodbc")
    def test_fetch_batch_returns_replay_records(self, mock_pyodbc: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pyodbc.connect.return_value = mock_conn

        mock_row = MagicMock()
        mock_row.ReplayId = 1
        mock_row.MessageId = 100
        mock_row.RawPayload = "MSH|^~\\&|..."
        mock_row.CorrelationId = "corr-1"
        mock_cursor.fetchall.return_value = [mock_row]

        result = self.client.fetch_batch("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], ReplayRecord)
        self.assertEqual(result[0].replay_id, 1)
        self.assertEqual(result[0].message_id, 100)
        self.assertEqual(result[0].raw_payload, "MSH|^~\\&|...")
        self.assertEqual(result[0].correlation_id, "corr-1")

    @patch("message_replay_job.db_client.pyodbc")
    def test_fetch_batch_returns_empty_list_when_no_rows(self, mock_pyodbc: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pyodbc.connect.return_value = mock_conn
        mock_cursor.fetchall.return_value = []

        result = self.client.fetch_batch("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

        self.assertEqual(result, [])

    @patch("message_replay_job.db_client.pyodbc")
    def test_fetch_batch_passes_correct_sql_and_params(self, mock_pyodbc: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pyodbc.connect.return_value = mock_conn
        mock_cursor.fetchall.return_value = []

        batch_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        self.client.fetch_batch(batch_id)

        sql_arg = mock_cursor.execute.call_args[0][0]
        params_arg = mock_cursor.execute.call_args[0][1]
        self.assertIn("WITH Batch AS", sql_arg)
        self.assertIn("ReplayBatchId = ?", sql_arg)
        self.assertEqual(params_arg, (batch_id,))

    @patch("message_replay_job.db_client.pyodbc")
    def test_fetch_batch_closes_connection_on_error(self, mock_pyodbc: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("DB error")
        mock_conn.cursor.return_value = mock_cursor
        mock_pyodbc.connect.return_value = mock_conn

        with self.assertRaises(Exception):
            self.client.fetch_batch("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

        mock_conn.close.assert_called_once()

    @patch("message_replay_job.db_client.pyodbc")
    def test_fetch_batch_reuses_connection(self, mock_pyodbc: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pyodbc.connect.return_value = mock_conn
        mock_cursor.fetchall.return_value = []

        self.client.fetch_batch("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
        self.client.fetch_batch("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

        mock_pyodbc.connect.assert_called_once()

    # ------------------------------------------------------------------
    # update_statuses — happy path
    # ------------------------------------------------------------------

    @patch("message_replay_job.db_client.pyodbc")
    def test_update_statuses_executes_correct_sql(self, mock_pyodbc: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pyodbc.connect.return_value = mock_conn

        self.client.update_statuses([1, 2, 3], "Loaded")

        sql_arg = mock_cursor.execute.call_args[0][0]
        params_arg = mock_cursor.execute.call_args[0][1]
        self.assertIn("UPDATE monitoring.MessageReplayQueue", sql_arg)
        self.assertIn("SET Status = ?", sql_arg)
        self.assertIn("?, ?, ?", sql_arg)
        self.assertEqual(params_arg, ["Loaded", 1, 2, 3])

    @patch("message_replay_job.db_client.pyodbc")
    def test_update_statuses_commits_on_success(self, mock_pyodbc: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pyodbc.connect.return_value = mock_conn

        self.client.update_statuses([1], "Loaded")

        mock_conn.commit.assert_called_once()

    @patch("message_replay_job.db_client.pyodbc")
    def test_update_statuses_rolls_back_on_error(self, mock_pyodbc: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("DB error")
        mock_conn.cursor.return_value = mock_cursor
        mock_pyodbc.connect.return_value = mock_conn

        with self.assertRaises(Exception):
            self.client.update_statuses([1, 2], "Loaded")

        mock_conn.rollback.assert_called_once()
        mock_conn.commit.assert_not_called()
        mock_conn.close.assert_called_once()

    @patch("message_replay_job.db_client.pyodbc")
    def test_update_statuses_single_id(self, mock_pyodbc: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pyodbc.connect.return_value = mock_conn

        self.client.update_statuses([42], "Failed")

        params_arg = mock_cursor.execute.call_args[0][1]
        self.assertEqual(params_arg, ["Failed", 42])
        mock_conn.commit.assert_called_once()

    @patch("message_replay_job.db_client.pyodbc")
    def test_update_statuses_skips_on_empty_list(self, mock_pyodbc: MagicMock) -> None:
        self.client.update_statuses([], "Loaded")
        mock_pyodbc.connect.assert_not_called()

    # ------------------------------------------------------------------
    # Auth mode selection
    # ------------------------------------------------------------------

    @patch("message_replay_job.db_client.pyodbc")
    def test_connect_uses_password_auth_when_password_set(self, mock_pyodbc: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = MagicMock()
        mock_pyodbc.connect.return_value = mock_conn
        mock_conn.cursor.return_value.fetchall.return_value = []

        self.client.fetch_batch("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

        conn_str = mock_pyodbc.connect.call_args[0][0]
        self.assertIn("UID=sa", conn_str)
        self.assertIn("PWD=secret", conn_str)

    @patch("message_replay_job.db_client.pyodbc")
    def test_connect_uses_managed_identity_when_no_password(self, mock_pyodbc: MagicMock) -> None:
        client = DatabaseClient(
            sql_server="myserver.database.windows.net",
            sql_database="IntegrationHub",
            sql_username=None,
            sql_password=None,
            sql_encrypt="yes",
            sql_trust_server_certificate="no",
        )
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = MagicMock()
        mock_pyodbc.connect.return_value = mock_conn
        mock_conn.cursor.return_value.fetchall.return_value = []

        client.fetch_batch("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

        conn_str = mock_pyodbc.connect.call_args[0][0]
        self.assertIn("Authentication=ActiveDirectoryMsi", conn_str)
        self.assertNotIn("UID=", conn_str)
        self.assertNotIn("PWD=", conn_str)
        client.close()

    @patch("message_replay_job.db_client.pyodbc")
    def test_connect_uses_user_assigned_mi_when_client_id_provided(self, mock_pyodbc: MagicMock) -> None:
        client = DatabaseClient(
            sql_server="myserver.database.windows.net",
            sql_database="IntegrationHub",
            sql_username=None,
            sql_password=None,
            sql_encrypt="yes",
            sql_trust_server_certificate="no",
            managed_identity_client_id="my-mi-client-id",
        )
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = MagicMock()
        mock_pyodbc.connect.return_value = mock_conn
        mock_conn.cursor.return_value.fetchall.return_value = []

        client.fetch_batch("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

        conn_str = mock_pyodbc.connect.call_args[0][0]
        self.assertIn("Authentication=ActiveDirectoryMsi", conn_str)
        self.assertIn("UID=my-mi-client-id", conn_str)
        self.assertNotIn("PWD=", conn_str)
        client.close()

    # ------------------------------------------------------------------
    # Reconnect-on-failure
    # ------------------------------------------------------------------

    @patch("message_replay_job.db_client.pyodbc")
    def test_connection_is_recreated_after_error(self, mock_pyodbc: MagicMock) -> None:
        mock_conn_1 = MagicMock()
        bad_cursor = MagicMock()
        bad_cursor.execute.side_effect = Exception("DB error")
        mock_conn_1.cursor.return_value = bad_cursor

        mock_conn_2 = MagicMock()
        good_cursor = MagicMock()
        good_cursor.fetchall.return_value = []
        mock_conn_2.cursor.return_value = good_cursor

        mock_pyodbc.connect.side_effect = [mock_conn_1, mock_conn_2]

        with self.assertRaises(Exception):
            self.client.fetch_batch("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

        mock_conn_1.close.assert_called_once()

        self.client.fetch_batch("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
        self.assertEqual(mock_pyodbc.connect.call_count, 2)

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def test_context_manager(self) -> None:
        with self.client as client:
            self.assertIsInstance(client, DatabaseClient)

    @patch("message_replay_job.db_client.pyodbc")
    def test_context_manager_closes_connection_on_exit(self, mock_pyodbc: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = MagicMock()
        mock_pyodbc.connect.return_value = mock_conn
        mock_conn.cursor.return_value.fetchall.return_value = []

        with self.client:
            self.client.fetch_batch("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
            mock_conn.close.assert_not_called()

        mock_conn.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
