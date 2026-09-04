import unittest
from unittest.mock import MagicMock, patch

from message_replay_job.db_client import DatabaseClient
from message_replay_job.replay_record import ReplayRecord
from message_replay_job.replay_status import ReplayStatus


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
        mock_row.SessionId = "mpi"
        mock_cursor.fetchall.return_value = [mock_row]

        result = self.client.fetch_batch("a1b2c3d4-e5f6-7890-abcd-ef1234567890", batch_size=100)

        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], ReplayRecord)
        self.assertEqual(result[0].replay_id, 1)
        self.assertEqual(result[0].message_id, 100)
        self.assertEqual(result[0].raw_payload, "MSH|^~\\&|...")
        self.assertEqual(result[0].correlation_id, "corr-1")
        self.assertEqual(result[0].session_id, "mpi")

    @patch("message_replay_job.db_client.pyodbc")
    def test_fetch_batch_returns_empty_list_when_no_rows(self, mock_pyodbc: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pyodbc.connect.return_value = mock_conn
        mock_cursor.fetchall.return_value = []

        result = self.client.fetch_batch("a1b2c3d4-e5f6-7890-abcd-ef1234567890", batch_size=100)

        self.assertEqual(result, [])

    @patch("message_replay_job.db_client.pyodbc")
    def test_fetch_batch_passes_correct_sql_and_params(self, mock_pyodbc: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pyodbc.connect.return_value = mock_conn
        mock_cursor.fetchall.return_value = []

        batch_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        self.client.fetch_batch(batch_id, batch_size=100)

        sql_arg = mock_cursor.execute.call_args[0][0]
        params_arg = mock_cursor.execute.call_args[0][1]
        self.assertIn("WITH Batch AS", sql_arg)
        self.assertIn("TOP (?)", sql_arg)
        self.assertIn("ReplayBatchId = ?", sql_arg)
        self.assertIn("ORDER BY b.ReplayId", sql_arg)
        self.assertEqual(params_arg, (100, batch_id))

    @patch("message_replay_job.db_client.pyodbc")
    def test_fetch_batch_closes_connection_on_error(self, mock_pyodbc: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("DB error")
        mock_conn.cursor.return_value = mock_cursor
        mock_pyodbc.connect.return_value = mock_conn

        with self.assertRaises(Exception):
            self.client.fetch_batch("a1b2c3d4-e5f6-7890-abcd-ef1234567890", batch_size=100)

        mock_conn.close.assert_called_once()

    @patch("message_replay_job.db_client.pyodbc")
    def test_fetch_batch_reuses_connection(self, mock_pyodbc: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pyodbc.connect.return_value = mock_conn
        mock_cursor.fetchall.return_value = []

        self.client.fetch_batch("a1b2c3d4-e5f6-7890-abcd-ef1234567890", batch_size=100)
        self.client.fetch_batch("a1b2c3d4-e5f6-7890-abcd-ef1234567890", batch_size=100)

        mock_pyodbc.connect.assert_called_once()

    @patch("message_replay_job.db_client.pyodbc")
    def test_fetch_batch_passes_custom_batch_size_as_first_param(self, mock_pyodbc: MagicMock) -> None:
        """batch_size must be passed as the first SQL parameter (TOP ?)."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pyodbc.connect.return_value = mock_conn
        mock_cursor.fetchall.return_value = []

        batch_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        self.client.fetch_batch(batch_id, batch_size=250)

        params_arg = mock_cursor.execute.call_args[0][1]
        self.assertEqual(params_arg[0], 250)
        self.assertEqual(params_arg[1], batch_id)

    # ------------------------------------------------------------------
    # update_statuses — happy path
    # ------------------------------------------------------------------

    @patch("message_replay_job.db_client.pyodbc")
    def test_update_statuses_executes_correct_sql(self, mock_pyodbc: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pyodbc.connect.return_value = mock_conn

        self.client.update_statuses([1, 2, 3], ReplayStatus.LOADED)

        sql_arg = mock_cursor.execute.call_args[0][0]
        params_arg = mock_cursor.execute.call_args[0][1]
        self.assertIn("UPDATE monitoring.MessageReplayQueue", sql_arg)
        self.assertIn("SET Status = ?", sql_arg)
        self.assertIn("?, ?, ?", sql_arg)
        self.assertEqual(params_arg, [ReplayStatus.LOADED, 1, 2, 3])

    @patch("message_replay_job.db_client.pyodbc")
    def test_update_statuses_commits_on_success(self, mock_pyodbc: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pyodbc.connect.return_value = mock_conn

        self.client.update_statuses([1], ReplayStatus.LOADED)

        mock_conn.commit.assert_called_once()

    @patch("message_replay_job.db_client.pyodbc")
    def test_update_statuses_rolls_back_on_error(self, mock_pyodbc: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("DB error")
        mock_conn.cursor.return_value = mock_cursor
        mock_pyodbc.connect.return_value = mock_conn

        with self.assertRaises(Exception):
            self.client.update_statuses([1, 2], ReplayStatus.LOADED)

        mock_conn.rollback.assert_called_once()
        mock_conn.commit.assert_not_called()
        mock_conn.close.assert_called_once()

    @patch("message_replay_job.db_client.pyodbc")
    def test_update_statuses_single_id(self, mock_pyodbc: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pyodbc.connect.return_value = mock_conn

        self.client.update_statuses([42], ReplayStatus.FAILED)

        params_arg = mock_cursor.execute.call_args[0][1]
        self.assertEqual(params_arg, [ReplayStatus.FAILED, 42])
        mock_conn.commit.assert_called_once()

    @patch("message_replay_job.db_client.pyodbc")
    def test_update_statuses_skips_on_empty_list(self, mock_pyodbc: MagicMock) -> None:
        self.client.update_statuses([], ReplayStatus.LOADED)
        mock_pyodbc.connect.assert_not_called()

    @patch("message_replay_job.db_client.pyodbc")
    def test_update_statuses_closes_connection_on_commit_error(self, mock_pyodbc: MagicMock) -> None:
        """If commit raises, the transaction must be rolled back and the connection discarded."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.commit.side_effect = Exception("Commit failed")
        mock_pyodbc.connect.return_value = mock_conn

        with self.assertRaises(Exception):
            self.client.update_statuses([1], ReplayStatus.LOADED)

        mock_conn.rollback.assert_called_once()
        mock_conn.close.assert_called_once()

    @patch("message_replay_job.db_client.pyodbc")
    def test_update_statuses_raises_original_error_when_rollback_also_fails(self, mock_pyodbc: MagicMock) -> None:
        """If rollback itself raises, the *original* error must still propagate.

        This guards against the rollback failure masking the root cause — the
        behaviour provided by wrapping rollback in its own try/except.
        """
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("original DB error")
        mock_conn.rollback.side_effect = Exception("rollback failed")
        mock_conn.cursor.return_value = mock_cursor
        mock_pyodbc.connect.return_value = mock_conn

        with self.assertRaises(Exception) as ctx:
            self.client.update_statuses([1], ReplayStatus.LOADED)

        # The *original* error must propagate, not the rollback error.
        self.assertIn("original DB error", str(ctx.exception))
        mock_conn.close.assert_called_once()

    # ------------------------------------------------------------------
    # Auth input validation
    # ------------------------------------------------------------------

    def test_raises_value_error_for_asymmetric_auth_inputs(self) -> None:
        """DatabaseClient must raise ValueError whenever exactly one of sql_username/sql_password is provided."""
        invalid_cases = [
            (None, "secret", "sql_username", "password set, username is None"),
            ("", "secret", "sql_username", "password set, username is empty string"),
            ("sa", None, "sql_password", "username set, password is None"),
            ("sa", "", "sql_password", "username set, password is empty string"),
        ]
        for username, password, expected_field, description in invalid_cases:
            with self.subTest(description):
                with self.assertRaises(ValueError) as ctx:
                    DatabaseClient(
                        sql_server="localhost,1433",
                        sql_database="IntegrationHub",
                        sql_username=username,
                        sql_password=password,
                        sql_encrypt="yes",
                        sql_trust_server_certificate="yes",
                    )
                self.assertIn(expected_field, str(ctx.exception))

    def test_no_error_for_valid_auth_inputs(self) -> None:
        """DatabaseClient must construct without error for symmetric auth inputs."""
        valid_cases = [
            ("sa", "secret", "both username and password provided"),  # nosec B106
            (None, None, "neither username nor password provided (Managed Identity)"),
        ]
        for username, password, description in valid_cases:
            with self.subTest(description):
                client = DatabaseClient(
                    sql_server="localhost,1433",
                    sql_database="IntegrationHub",
                    sql_username=username,
                    sql_password=password,
                    sql_encrypt="yes",
                    sql_trust_server_certificate="yes",
                )
                client.close()

    # ------------------------------------------------------------------
    # Auth mode selection
    # ------------------------------------------------------------------

    @patch("message_replay_job.db_client.pyodbc")
    def test_connect_uses_password_auth_when_password_set(self, mock_pyodbc: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = MagicMock()
        mock_pyodbc.connect.return_value = mock_conn
        mock_conn.cursor.return_value.fetchall.return_value = []

        self.client.fetch_batch("a1b2c3d4-e5f6-7890-abcd-ef1234567890", batch_size=100)

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

        client.fetch_batch("a1b2c3d4-e5f6-7890-abcd-ef1234567890", batch_size=100)

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

        client.fetch_batch("a1b2c3d4-e5f6-7890-abcd-ef1234567890", batch_size=100)

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
            self.client.fetch_batch("a1b2c3d4-e5f6-7890-abcd-ef1234567890", batch_size=100)

        mock_conn_1.close.assert_called_once()

        self.client.fetch_batch("a1b2c3d4-e5f6-7890-abcd-ef1234567890", batch_size=100)
        self.assertEqual(mock_pyodbc.connect.call_count, 2)

    @patch("message_replay_job.db_client.pyodbc")
    def test_explicit_close_releases_connection(self, mock_pyodbc: MagicMock) -> None:
        """Calling close() must close and discard the cached connection; the next call reconnects."""
        mock_conn_1 = MagicMock()
        mock_conn_1.cursor.return_value = MagicMock()
        mock_conn_1.cursor.return_value.fetchall.return_value = []
        mock_pyodbc.connect.return_value = mock_conn_1

        self.client.fetch_batch("a1b2c3d4-e5f6-7890-abcd-ef1234567890", batch_size=100)
        self.client.close()
        mock_conn_1.close.assert_called_once()

        # Subsequent call must open a fresh connection
        mock_pyodbc.connect.reset_mock()
        mock_conn_2 = MagicMock()
        mock_conn_2.cursor.return_value = MagicMock()
        mock_conn_2.cursor.return_value.fetchall.return_value = []
        mock_pyodbc.connect.return_value = mock_conn_2

        self.client.fetch_batch("a1b2c3d4-e5f6-7890-abcd-ef1234567890", batch_size=100)
        mock_pyodbc.connect.assert_called_once()

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
            self.client.fetch_batch("a1b2c3d4-e5f6-7890-abcd-ef1234567890", batch_size=100)
            mock_conn.close.assert_not_called()

        mock_conn.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
