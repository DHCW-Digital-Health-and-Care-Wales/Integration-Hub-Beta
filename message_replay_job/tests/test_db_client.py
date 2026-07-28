import unittest
import uuid
from unittest.mock import MagicMock, patch

from message_replay_job.db_client import DatabaseClient
from message_replay_job.replay_record import ReplayRecord
from message_replay_job.replay_status import ReplayStatus

BATCH_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"


class TestDatabaseClient(unittest.TestCase):
    """Tests for DatabaseClient with mocked psycopg."""

    def setUp(self) -> None:
        self.client = DatabaseClient(  # nosec B106 — test fixture, not real credentials
            pg_host="localhost",
            pg_port=5432,
            pg_database="integrationhub",
            pg_user="inthub",
            pg_password="secret",
            pg_sslmode="disable",
        )

    def tearDown(self) -> None:
        self.client.close()

    # ------------------------------------------------------------------
    # fetch_batch — happy path
    # ------------------------------------------------------------------

    @patch("message_replay_job.db_client.psycopg")
    def test_fetch_batch_returns_replay_records(self, mock_psycopg: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        # psycopg returns dict rows (dict_row factory), not attribute-style pyodbc rows.
        mock_cursor.fetchall.return_value = [
            {
                "replay_id": 1,
                "message_id": 100,
                "raw_payload": "MSH|^~\\&|...",
                "correlation_id": "corr-1",
                "session_id": "mpi",
            }
        ]

        result = self.client.fetch_batch(BATCH_ID, batch_size=100)

        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], ReplayRecord)
        self.assertEqual(result[0].replay_id, 1)
        self.assertEqual(result[0].message_id, 100)
        self.assertEqual(result[0].raw_payload, "MSH|^~\\&|...")
        self.assertEqual(result[0].correlation_id, "corr-1")
        self.assertEqual(result[0].session_id, "mpi")

    @patch("message_replay_job.db_client.psycopg")
    def test_fetch_batch_returns_empty_list_when_no_rows(self, mock_psycopg: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn
        mock_cursor.fetchall.return_value = []

        result = self.client.fetch_batch(BATCH_ID, batch_size=100)

        self.assertEqual(result, [])

    @patch("message_replay_job.db_client.psycopg")
    def test_fetch_batch_passes_correct_sql_and_params(self, mock_psycopg: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn
        mock_cursor.fetchall.return_value = []

        self.client.fetch_batch(BATCH_ID, batch_size=100)

        sql_arg = mock_cursor.execute.call_args[0][0]
        params_arg = mock_cursor.execute.call_args[0][1]
        self.assertIn("WITH batch AS", sql_arg)
        self.assertIn("LIMIT %s", sql_arg)
        self.assertIn("replay_batch_id = %s", sql_arg)
        self.assertIn("ORDER BY b.replay_id", sql_arg)
        # PostgreSQL equivalent of the T-SQL READPAST hint.
        self.assertIn("FOR UPDATE SKIP LOCKED", sql_arg)
        # Parameter order is (batch_id, batch_size): LIMIT now follows the WHERE clause,
        # whereas T-SQL's TOP (?) came first.
        self.assertEqual(params_arg, (uuid.UUID(BATCH_ID), 100))

    def test_fetch_batch_rejects_invalid_batch_id(self) -> None:
        """replay_batch_id targets a uuid column, so a malformed value must fail fast."""
        with self.assertRaises(ValueError):
            self.client.fetch_batch("not-a-uuid", batch_size=100)

    @patch("message_replay_job.db_client.psycopg")
    def test_fetch_batch_closes_connection_on_error(self, mock_psycopg: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("DB error")
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        with self.assertRaises(Exception):
            self.client.fetch_batch(BATCH_ID, batch_size=100)

        mock_conn.close.assert_called_once()

    @patch("message_replay_job.db_client.psycopg")
    def test_fetch_batch_reuses_connection(self, mock_psycopg: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn
        mock_cursor.fetchall.return_value = []

        self.client.fetch_batch(BATCH_ID, batch_size=100)
        self.client.fetch_batch(BATCH_ID, batch_size=100)

        mock_psycopg.connect.assert_called_once()

    @patch("message_replay_job.db_client.psycopg")
    def test_fetch_batch_passes_custom_batch_size_as_limit_param(self, mock_psycopg: MagicMock) -> None:
        """batch_size must be passed as the second SQL parameter (LIMIT %s)."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn
        mock_cursor.fetchall.return_value = []

        self.client.fetch_batch(BATCH_ID, batch_size=250)

        params_arg = mock_cursor.execute.call_args[0][1]
        self.assertEqual(params_arg[0], uuid.UUID(BATCH_ID))
        self.assertEqual(params_arg[1], 250)

    # ------------------------------------------------------------------
    # update_statuses — happy path
    # ------------------------------------------------------------------

    @patch("message_replay_job.db_client.psycopg")
    def test_update_statuses_executes_correct_sql(self, mock_psycopg: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        self.client.update_statuses([1, 2, 3], ReplayStatus.LOADED)

        sql_arg = mock_cursor.execute.call_args[0][0]
        params_arg = mock_cursor.execute.call_args[0][1]
        self.assertIn("UPDATE monitoring.message_replay_queue", sql_arg)
        self.assertIn("SET status = %s", sql_arg)
        # A single ANY(%s) array predicate replaces the variable-length IN (?, ?, ?) list.
        self.assertIn("replay_id = ANY(%s)", sql_arg)
        self.assertEqual(params_arg, [ReplayStatus.LOADED, [1, 2, 3]])

    @patch("message_replay_job.db_client.psycopg")
    def test_update_statuses_commits_on_success(self, mock_psycopg: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        self.client.update_statuses([1], ReplayStatus.LOADED)

        mock_conn.commit.assert_called_once()

    @patch("message_replay_job.db_client.psycopg")
    def test_update_statuses_rolls_back_on_error(self, mock_psycopg: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("DB error")
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        with self.assertRaises(Exception):
            self.client.update_statuses([1, 2], ReplayStatus.LOADED)

        mock_conn.rollback.assert_called_once()
        mock_conn.commit.assert_not_called()
        mock_conn.close.assert_called_once()

    @patch("message_replay_job.db_client.psycopg")
    def test_update_statuses_single_id(self, mock_psycopg: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        self.client.update_statuses([42], ReplayStatus.FAILED)

        params_arg = mock_cursor.execute.call_args[0][1]
        self.assertEqual(params_arg, [ReplayStatus.FAILED, [42]])
        mock_conn.commit.assert_called_once()

    @patch("message_replay_job.db_client.psycopg")
    def test_update_statuses_skips_on_empty_list(self, mock_psycopg: MagicMock) -> None:
        self.client.update_statuses([], ReplayStatus.LOADED)
        mock_psycopg.connect.assert_not_called()

    @patch("message_replay_job.db_client.psycopg")
    def test_update_statuses_closes_connection_on_commit_error(self, mock_psycopg: MagicMock) -> None:
        """If commit raises, the transaction must be rolled back and the connection discarded."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.commit.side_effect = Exception("Commit failed")
        mock_psycopg.connect.return_value = mock_conn

        with self.assertRaises(Exception):
            self.client.update_statuses([1], ReplayStatus.LOADED)

        mock_conn.rollback.assert_called_once()
        mock_conn.close.assert_called_once()

    @patch("message_replay_job.db_client.psycopg")
    def test_update_statuses_raises_original_error_when_rollback_also_fails(self, mock_psycopg: MagicMock) -> None:
        """If rollback itself raises, the *original* error must still propagate.

        This guards against the rollback failure masking the root cause — the
        behaviour provided by wrapping rollback in its own try/except.
        """
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("original DB error")
        mock_conn.rollback.side_effect = Exception("rollback failed")
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        with self.assertRaises(Exception) as ctx:
            self.client.update_statuses([1], ReplayStatus.LOADED)

        # The *original* error must propagate, not the rollback error.
        self.assertIn("original DB error", str(ctx.exception))
        mock_conn.close.assert_called_once()

    # ------------------------------------------------------------------
    # Auth input validation
    # ------------------------------------------------------------------

    def test_raises_value_error_when_user_missing(self) -> None:
        """DatabaseClient must raise ValueError when pg_user is absent.

        Unlike SQL Server's ActiveDirectoryMsi mode, PostgreSQL always needs a role
        name, so pg_user is required regardless of which auth mode is in play.
        """
        invalid_cases = [
            (None, "password provided, user is None"),
            ("", "password provided, user is empty string"),
        ]
        for user, description in invalid_cases:
            with self.subTest(description):
                with self.assertRaises(ValueError) as ctx:
                    DatabaseClient(
                        pg_host="localhost",
                        pg_database="integrationhub",
                        pg_user=user,  # type: ignore[arg-type]
                        pg_password="secret",  # nosec B106 — test fixture
                    )
                self.assertIn("pg_user", str(ctx.exception))

    def test_no_error_for_valid_auth_inputs(self) -> None:
        """Both auth modes must construct without error."""
        valid_cases = [
            ("secret", "password provided (password auth)"),  # nosec B106
            (None, "no password provided (Managed Identity)"),
        ]
        for password, description in valid_cases:
            with self.subTest(description):
                client = DatabaseClient(
                    pg_host="localhost",
                    pg_database="integrationhub",
                    pg_user="inthub",
                    pg_password=password,
                )
                client.close()

    # ------------------------------------------------------------------
    # Auth mode selection
    # ------------------------------------------------------------------

    @patch("message_replay_job.db_client.psycopg")
    def test_connect_uses_password_auth_when_password_set(self, mock_psycopg: MagicMock) -> None:
        """When pg_password is provided it is used directly, with no token acquisition."""
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = MagicMock()
        mock_psycopg.connect.return_value = mock_conn
        mock_conn.cursor.return_value.fetchall.return_value = []

        with patch("message_replay_job.db_client.fetch_entra_access_token") as mock_token:
            self.client.fetch_batch(BATCH_ID, batch_size=100)
            mock_token.assert_not_called()

        kwargs = mock_psycopg.connect.call_args.kwargs
        self.assertEqual(kwargs["user"], "inthub")
        self.assertEqual(kwargs["password"], "secret")
        self.assertEqual(kwargs["host"], "localhost")
        self.assertEqual(kwargs["port"], 5432)
        self.assertEqual(kwargs["dbname"], "integrationhub")
        self.assertEqual(kwargs["sslmode"], "disable")
        self.assertFalse(kwargs["autocommit"])

    @patch("message_replay_job.db_client.fetch_entra_access_token")
    @patch("message_replay_job.db_client.psycopg")
    def test_connect_uses_entra_token_as_password_when_no_password(
        self, mock_psycopg: MagicMock, mock_token: MagicMock
    ) -> None:
        """With no password, an Entra token is fetched and passed as the password."""
        mock_token.return_value = "entra-token-value"
        client = DatabaseClient(
            pg_host="myserver.postgres.database.azure.com",
            pg_database="integrationhub",
            pg_user="replay-identity",
            pg_password=None,
        )
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = MagicMock()
        mock_psycopg.connect.return_value = mock_conn
        mock_conn.cursor.return_value.fetchall.return_value = []

        client.fetch_batch(BATCH_ID, batch_size=100)

        mock_token.assert_called_once_with(None)
        kwargs = mock_psycopg.connect.call_args.kwargs
        self.assertEqual(kwargs["password"], "entra-token-value")
        self.assertEqual(kwargs["user"], "replay-identity")
        # SSL must not be silently downgraded for a cloud connection.
        self.assertEqual(kwargs["sslmode"], "require")
        client.close()

    @patch("message_replay_job.db_client.fetch_entra_access_token")
    @patch("message_replay_job.db_client.psycopg")
    def test_connect_passes_client_id_for_user_assigned_identity(
        self, mock_psycopg: MagicMock, mock_token: MagicMock
    ) -> None:
        """When managed_identity_client_id is set it is forwarded to the token helper."""
        mock_token.return_value = "entra-token-value"
        client = DatabaseClient(
            pg_host="myserver.postgres.database.azure.com",
            pg_database="integrationhub",
            pg_user="replay-identity",
            pg_password=None,
            managed_identity_client_id="my-mi-client-id",
        )
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = MagicMock()
        mock_psycopg.connect.return_value = mock_conn
        mock_conn.cursor.return_value.fetchall.return_value = []

        client.fetch_batch(BATCH_ID, batch_size=100)

        mock_token.assert_called_once_with("my-mi-client-id")
        self.assertEqual(mock_psycopg.connect.call_args.kwargs["password"], "entra-token-value")
        client.close()

    # ------------------------------------------------------------------
    # Reconnect-on-failure
    # ------------------------------------------------------------------

    @patch("message_replay_job.db_client.psycopg")
    def test_connection_is_recreated_after_error(self, mock_psycopg: MagicMock) -> None:
        mock_conn_1 = MagicMock()
        bad_cursor = MagicMock()
        bad_cursor.execute.side_effect = Exception("DB error")
        mock_conn_1.cursor.return_value = bad_cursor

        mock_conn_2 = MagicMock()
        good_cursor = MagicMock()
        good_cursor.fetchall.return_value = []
        mock_conn_2.cursor.return_value = good_cursor

        mock_psycopg.connect.side_effect = [mock_conn_1, mock_conn_2]

        with self.assertRaises(Exception):
            self.client.fetch_batch("a1b2c3d4-e5f6-7890-abcd-ef1234567890", batch_size=100)

        mock_conn_1.close.assert_called_once()

        self.client.fetch_batch("a1b2c3d4-e5f6-7890-abcd-ef1234567890", batch_size=100)
        self.assertEqual(mock_psycopg.connect.call_count, 2)

    @patch("message_replay_job.db_client.psycopg")
    def test_explicit_close_releases_connection(self, mock_psycopg: MagicMock) -> None:
        """Calling close() must close and discard the cached connection; the next call reconnects."""
        mock_conn_1 = MagicMock()
        mock_conn_1.cursor.return_value = MagicMock()
        mock_conn_1.cursor.return_value.fetchall.return_value = []
        mock_psycopg.connect.return_value = mock_conn_1

        self.client.fetch_batch("a1b2c3d4-e5f6-7890-abcd-ef1234567890", batch_size=100)
        self.client.close()
        mock_conn_1.close.assert_called_once()

        # Subsequent call must open a fresh connection
        mock_psycopg.connect.reset_mock()
        mock_conn_2 = MagicMock()
        mock_conn_2.cursor.return_value = MagicMock()
        mock_conn_2.cursor.return_value.fetchall.return_value = []
        mock_psycopg.connect.return_value = mock_conn_2

        self.client.fetch_batch("a1b2c3d4-e5f6-7890-abcd-ef1234567890", batch_size=100)
        mock_psycopg.connect.assert_called_once()

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def test_context_manager(self) -> None:
        with self.client as client:
            self.assertIsInstance(client, DatabaseClient)

    @patch("message_replay_job.db_client.psycopg")
    def test_context_manager_closes_connection_on_exit(self, mock_psycopg: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = MagicMock()
        mock_psycopg.connect.return_value = mock_conn
        mock_conn.cursor.return_value.fetchall.return_value = []

        with self.client:
            self.client.fetch_batch("a1b2c3d4-e5f6-7890-abcd-ef1234567890", batch_size=100)
            mock_conn.close.assert_not_called()

        mock_conn.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
