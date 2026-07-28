import unittest
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import MagicMock, patch

from message_store_service.db_client import DatabaseClient
from message_store_service.message_record import MessageRecord


def _make_record(
    received_at: datetime = datetime.now(timezone.utc),
    correlation_id: str = "corr-1",
    source_system: str = "SRC",
    processing_component: str = "message_store_service",
    target_system: Optional[str] = None,
    raw_payload: str = "MSH|...",
    xml_payload: Optional[str] = None,
    session_id: str = "test-session",
) -> MessageRecord:
    """Helper to create a MessageRecord with sensible defaults."""
    return MessageRecord(
        received_at=received_at,
        correlation_id=correlation_id,
        source_system=source_system,
        processing_component=processing_component,
        target_system=target_system,
        raw_payload=raw_payload,
        xml_payload=xml_payload,
        session_id=session_id,
    )


class TestDatabaseClient(unittest.TestCase):
    """Tests for DatabaseClient.store_messages with mocked psycopg."""

    def setUp(self) -> None:
        self.client = DatabaseClient(
            pg_host="localhost",
            pg_port=5432,
            pg_database="integrationhub",
            pg_user="inthub",
            pg_password="secret",  # nosec B106 — test fixture, not real password
            pg_sslmode="disable",
        )

    def tearDown(self) -> None:
        # Close any cached connection so tests do not share connection state.
        self.client.close()

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    @patch("message_store_service.db_client.psycopg")
    def test_store_messages_calls_executemany_and_commit(self, mock_psycopg: MagicMock) -> None:
        """Verify executemany is called with the correct rows and commit fires.

        The persistent connection must NOT be closed after a successful insert.
        """
        # Arrange
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        record = _make_record()

        # Act
        self.client.store_messages([record])

        # Assert
        mock_cursor.executemany.assert_called_once()
        sql_arg = mock_cursor.executemany.call_args[0][0]
        self.assertIn("INSERT INTO monitoring.message", sql_arg)

        rows_arg = mock_cursor.executemany.call_args[0][1]
        self.assertEqual(len(rows_arg), 1)
        self.assertEqual(rows_arg[0][2], "corr-1")  # correlation_id

        mock_conn.commit.assert_called_once()
        # Connection is kept alive for reuse — must NOT be closed here.
        mock_conn.close.assert_not_called()

    @patch("message_store_service.db_client.datetime")
    @patch("message_store_service.db_client.psycopg")
    def test_store_messages_batch_inserts_multiple_records(self, mock_psycopg: MagicMock, mock_dt: MagicMock) -> None:
        """Verify multiple records are inserted as a single executemany batch with correct per-row values."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        fixed_stored_at = datetime(2025, 6, 1, 10, 0, 1, tzinfo=timezone.utc)
        mock_dt.now.return_value = fixed_stored_at

        records = [
            MessageRecord(
                received_at=datetime(2025, 6, 1, 9, 0, i, tzinfo=timezone.utc),
                correlation_id=f"corr-{i}",
                source_system=f"SRC-{i}",
                processing_component=f"comp-{i}",
                target_system=f"tgt-{i}" if i % 2 == 0 else None,
                raw_payload=f"MSH|payload-{i}",
                xml_payload=f"<msg id='{i}'/>" if i % 2 == 0 else None,
                session_id=f"session-{i}",
            )
            for i in range(5)
        ]

        self.client.store_messages(records)

        rows_arg = mock_cursor.executemany.call_args[0][1]
        self.assertEqual(len(rows_arg), 5)
        mock_conn.commit.assert_called_once()
        mock_conn.close.assert_not_called()

        for i, (row, record) in enumerate(zip(rows_arg, records)):
            self.assertEqual(row[0], record.received_at, f"row {i}: received_at mismatch")
            self.assertEqual(row[1], fixed_stored_at, f"row {i}: stored_at must equal the batch timestamp")
            self.assertEqual(row[2], record.correlation_id, f"row {i}: correlation_id mismatch")
            self.assertEqual(row[3], record.source_system, f"row {i}: source_system mismatch")
            self.assertEqual(row[4], record.processing_component, f"row {i}: processing_component mismatch")
            self.assertEqual(row[5], record.target_system, f"row {i}: target_system mismatch")
            self.assertEqual(row[6], record.raw_payload, f"row {i}: raw_payload mismatch")
            self.assertEqual(row[7], record.xml_payload, f"row {i}: xml_payload mismatch")
            self.assertEqual(row[8], record.session_id, f"row {i}: session_id mismatch")

    # ------------------------------------------------------------------
    # Connection reuse
    # ------------------------------------------------------------------

    @patch("message_store_service.db_client.psycopg")
    def test_connection_is_reused_across_store_messages_calls(self, mock_psycopg: MagicMock) -> None:
        """A second store_messages call must reuse the same connection without reconnecting."""
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = MagicMock()
        mock_psycopg.connect.return_value = mock_conn

        self.client.store_messages([_make_record()])
        self.client.store_messages([_make_record()])

        # psycopg.connect should only have been called once
        mock_psycopg.connect.assert_called_once()

    @patch("message_store_service.db_client.psycopg")
    def test_connection_is_recreated_after_error(self, mock_psycopg: MagicMock) -> None:
        """After a DB error the stale connection is discarded; the next call opens a fresh one."""
        # First call: executemany blows up
        mock_conn_1 = MagicMock()
        bad_cursor = MagicMock()
        bad_cursor.executemany.side_effect = Exception("DB error")
        mock_conn_1.cursor.return_value = bad_cursor

        # Second call: works fine
        mock_conn_2 = MagicMock()
        mock_conn_2.cursor.return_value = MagicMock()

        mock_psycopg.connect.side_effect = [mock_conn_1, mock_conn_2]

        with self.assertRaises(Exception):
            self.client.store_messages([_make_record()])

        # Connection 1 should have been discarded
        mock_conn_1.close.assert_called_once()

        # Second call should succeed and use a brand-new connection
        self.client.store_messages([_make_record()])
        self.assertEqual(mock_psycopg.connect.call_count, 2)
        mock_conn_2.commit.assert_called_once()

    @patch("message_store_service.db_client.psycopg")
    def test_explicit_close_releases_connection(self, mock_psycopg: MagicMock) -> None:
        """Calling close() must close and discard the cached connection."""
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = MagicMock()
        mock_psycopg.connect.return_value = mock_conn

        self.client.store_messages([_make_record()])
        self.client.close()

        mock_conn.close.assert_called_once()
        # A subsequent store_messages call must reconnect
        mock_psycopg.connect.reset_mock()
        mock_conn_2 = MagicMock()
        mock_conn_2.cursor.return_value = MagicMock()
        mock_psycopg.connect.return_value = mock_conn_2

        self.client.store_messages([_make_record()])
        mock_psycopg.connect.assert_called_once()

    # ------------------------------------------------------------------
    # Empty batch
    # ------------------------------------------------------------------

    @patch("message_store_service.db_client.psycopg")
    def test_store_messages_skips_insert_on_empty_list(self, mock_psycopg: MagicMock) -> None:
        """An empty message list should not open a connection or execute SQL."""
        self.client.store_messages([])
        mock_psycopg.connect.assert_not_called()

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    @patch("message_store_service.db_client.psycopg")
    def test_store_messages_rolls_back_on_executemany_error(self, mock_psycopg: MagicMock) -> None:
        """If executemany raises, the transaction must be rolled back, the error re-raised,
        and the stale connection discarded so the next call reconnects."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.executemany.side_effect = Exception("DB error")
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        with self.assertRaises(Exception) as ctx:
            self.client.store_messages([_make_record()])

        self.assertIn("DB error", str(ctx.exception))
        mock_conn.rollback.assert_called_once()
        mock_conn.commit.assert_not_called()
        # Connection must be closed so the next call reconnects cleanly.
        mock_conn.close.assert_called_once()

    @patch("message_store_service.db_client.psycopg")
    def test_store_messages_closes_connection_on_commit_error(self, mock_psycopg: MagicMock) -> None:
        """If commit raises, the connection must be rolled back and discarded."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.commit.side_effect = Exception("Commit failed")
        mock_psycopg.connect.return_value = mock_conn

        with self.assertRaises(Exception):
            self.client.store_messages([_make_record()])

        mock_conn.rollback.assert_called_once()
        mock_conn.close.assert_called_once()

    @patch("message_store_service.db_client.psycopg")
    def test_store_messages_raises_original_error_when_rollback_also_fails(self, mock_psycopg: MagicMock) -> None:
        """If rollback itself raises (e.g. broken connection), the *original* insert error must
        still be re-raised and the stale connection must still be discarded.

        This guards against the rollback failure masking the root cause.
        """
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        # The original failure
        mock_cursor.executemany.side_effect = Exception("original DB error")
        # Rollback also fails (connection is broken)
        mock_conn.rollback.side_effect = Exception("rollback failed")
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        with self.assertRaises(Exception) as ctx:
            self.client.store_messages([_make_record()])

        # The *original* error must propagate, not the rollback error.
        self.assertIn("original DB error", str(ctx.exception))
        mock_conn.rollback.assert_called_once()
        mock_conn.close.assert_called_once()

    @patch("message_store_service.db_client.psycopg")
    def test_store_messages_raises_on_connection_failure(self, mock_psycopg: MagicMock) -> None:
        """If psycopg.connect itself fails, the error propagates."""
        mock_psycopg.connect.side_effect = Exception("Connection refused")

        with self.assertRaises(Exception) as ctx:
            self.client.store_messages([_make_record()])

        self.assertIn("Connection refused", str(ctx.exception))

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
        """Both auth modes must construct without error.

        A password means password auth; no password means Managed Identity auth.
        """
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

    @patch("message_store_service.db_client.psycopg")
    def test_connect_uses_password_auth_when_password_set(self, mock_psycopg: MagicMock) -> None:
        """When pg_password is provided it is used directly, with no token acquisition."""
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = MagicMock()
        mock_psycopg.connect.return_value = mock_conn

        with patch("message_store_service.db_client.fetch_entra_access_token") as mock_token:
            self.client.store_messages([_make_record()])
            mock_token.assert_not_called()

        kwargs = mock_psycopg.connect.call_args.kwargs
        self.assertEqual(kwargs["user"], "inthub")
        self.assertEqual(kwargs["password"], "secret")
        self.assertEqual(kwargs["host"], "localhost")
        self.assertEqual(kwargs["port"], 5432)
        self.assertEqual(kwargs["dbname"], "integrationhub")
        self.assertEqual(kwargs["sslmode"], "disable")
        self.assertFalse(kwargs["autocommit"])

    @patch("message_store_service.db_client.fetch_entra_access_token")
    @patch("message_store_service.db_client.psycopg")
    def test_connect_uses_entra_token_as_password_when_no_password(
        self, mock_psycopg: MagicMock, mock_token: MagicMock
    ) -> None:
        """With no password, an Entra token is fetched and passed as the password.

        System-assigned identity: no client ID is passed to the token helper.
        """
        mock_token.return_value = "entra-token-value"
        client = DatabaseClient(
            pg_host="myserver.postgres.database.azure.com",
            pg_database="integrationhub",
            pg_user="message-store-identity",
            pg_password=None,
        )
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = MagicMock()
        mock_psycopg.connect.return_value = mock_conn

        client.store_messages([_make_record()])

        mock_token.assert_called_once_with(None)
        kwargs = mock_psycopg.connect.call_args.kwargs
        self.assertEqual(kwargs["password"], "entra-token-value")
        self.assertEqual(kwargs["user"], "message-store-identity")
        # SSL must not be silently downgraded for a cloud connection.
        self.assertEqual(kwargs["sslmode"], "require")
        client.close()

    @patch("message_store_service.db_client.fetch_entra_access_token")
    @patch("message_store_service.db_client.psycopg")
    def test_connect_passes_client_id_for_user_assigned_identity(
        self, mock_psycopg: MagicMock, mock_token: MagicMock
    ) -> None:
        """When managed_identity_client_id is set it is forwarded to the token helper."""
        mock_token.return_value = "entra-token-value"
        client = DatabaseClient(
            pg_host="myserver.postgres.database.azure.com",
            pg_database="integrationhub",
            pg_user="message-store-identity",
            pg_password=None,
            managed_identity_client_id="my-mi-client-id",
        )
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = MagicMock()
        mock_psycopg.connect.return_value = mock_conn

        client.store_messages([_make_record()])

        mock_token.assert_called_once_with("my-mi-client-id")
        self.assertEqual(mock_psycopg.connect.call_args.kwargs["password"], "entra-token-value")
        client.close()

    @patch("message_store_service.db_client.fetch_entra_access_token")
    @patch("message_store_service.db_client.psycopg")
    def test_token_is_refetched_on_reconnect(self, mock_psycopg: MagicMock, mock_token: MagicMock) -> None:
        """Entra tokens expire, so a fresh one must be acquired on every reconnect."""
        mock_token.side_effect = ["token-1", "token-2"]

        client = DatabaseClient(
            pg_host="myserver.postgres.database.azure.com",
            pg_database="integrationhub",
            pg_user="message-store-identity",
            pg_password=None,
        )

        # First connection fails during insert, forcing the connection to be discarded.
        bad_conn = MagicMock()
        bad_cursor = MagicMock()
        bad_cursor.executemany.side_effect = Exception("DB error")
        bad_conn.cursor.return_value = bad_cursor

        good_conn = MagicMock()
        good_conn.cursor.return_value = MagicMock()
        mock_psycopg.connect.side_effect = [bad_conn, good_conn]

        with self.assertRaises(Exception):
            client.store_messages([_make_record()])
        client.store_messages([_make_record()])

        self.assertEqual(mock_token.call_count, 2)
        self.assertEqual(mock_psycopg.connect.call_args_list[0].kwargs["password"], "token-1")
        self.assertEqual(mock_psycopg.connect.call_args_list[1].kwargs["password"], "token-2")
        client.close()

    # ------------------------------------------------------------------
    # Row content correctness
    # ------------------------------------------------------------------

    @patch("message_store_service.db_client.datetime")
    @patch("message_store_service.db_client.psycopg")
    def test_store_messages_row_tuple_matches_column_order(self, mock_psycopg: MagicMock, mock_dt: MagicMock) -> None:
        """Verify the tuple order matches the INSERT column order and stored_at is injected by db_client."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        fixed_stored_at = datetime(2025, 6, 1, 10, 0, 1, tzinfo=timezone.utc)
        mock_dt.now.return_value = fixed_stored_at

        received_at = datetime(2025, 6, 1, 9, 59, 0, tzinfo=timezone.utc)

        record = MessageRecord(
            received_at=received_at,
            correlation_id="cid",
            source_system="src",
            processing_component="comp",
            target_system="tgt",
            raw_payload="raw",
            xml_payload="<xml/>",
            session_id="test-session",
        )

        self.client.store_messages([record])

        row = mock_cursor.executemany.call_args[0][1][0]
        # Column order: ReceivedAt, StoredAt, CorrelationId, SourceSystem,
        #               ProcessingComponent, TargetSystem, RawPayload, XmlPayload, SessionId
        self.assertEqual(
            row, (received_at, fixed_stored_at, "cid", "src", "comp", "tgt", "raw", "<xml/>", "test-session")
        )

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def test_context_manager(self) -> None:
        """Verify DatabaseClient can be used as a context manager."""
        with self.client as client:
            self.assertIsInstance(client, DatabaseClient)

    @patch("message_store_service.db_client.psycopg")
    def test_context_manager_closes_connection_on_exit(self, mock_psycopg: MagicMock) -> None:
        """__exit__ must close and discard the persistent connection."""
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = MagicMock()
        mock_psycopg.connect.return_value = mock_conn

        with self.client:
            self.client.store_messages([_make_record()])
            # Connection open, not yet closed
            mock_conn.close.assert_not_called()

        # Connection should be closed once the context exits
        mock_conn.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
