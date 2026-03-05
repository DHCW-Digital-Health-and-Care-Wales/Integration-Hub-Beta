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
    )


class TestDatabaseClient(unittest.TestCase):
    """Tests for DatabaseClient.store_messages with mocked pyodbc."""

    def setUp(self) -> None:
        self.client = DatabaseClient(
            sql_server="localhost,1433",
            sql_database="IntegrationHub",
            sql_username="sa",
            sql_password="secret",
            sql_encrypt="yes",
            sql_trust_server_certificate="yes",
        )

    def tearDown(self) -> None:
        # Close any cached connection so tests do not share connection state.
        self.client.close()

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    @patch("message_store_service.db_client.pyodbc")
    def test_store_messages_calls_executemany_and_commit(self, mock_pyodbc: MagicMock) -> None:
        """Verify fast_executemany is enabled, executemany is called with correct rows, and commit fires.

        The persistent connection must NOT be closed after a successful insert.
        """
        # Arrange
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pyodbc.connect.return_value = mock_conn

        record = _make_record()

        # Act
        self.client.store_messages([record])

        # Assert
        self.assertTrue(mock_cursor.fast_executemany)
        mock_cursor.executemany.assert_called_once()
        sql_arg = mock_cursor.executemany.call_args[0][0]
        self.assertIn("INSERT INTO monitoring.Message", sql_arg)

        rows_arg = mock_cursor.executemany.call_args[0][1]
        self.assertEqual(len(rows_arg), 1)
        self.assertEqual(rows_arg[0][2], "corr-1")  # correlation_id

        mock_conn.commit.assert_called_once()
        # Connection is kept alive for reuse — must NOT be closed here.
        mock_conn.close.assert_not_called()

    @patch("message_store_service.db_client.datetime")
    @patch("message_store_service.db_client.pyodbc")
    def test_store_messages_batch_inserts_multiple_records(
        self, mock_pyodbc: MagicMock, mock_dt: MagicMock
    ) -> None:
        """Verify multiple records are inserted as a single executemany batch with correct per-row values."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pyodbc.connect.return_value = mock_conn

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

    # ------------------------------------------------------------------
    # Connection reuse
    # ------------------------------------------------------------------

    @patch("message_store_service.db_client.pyodbc")
    def test_connection_is_reused_across_store_messages_calls(self, mock_pyodbc: MagicMock) -> None:
        """A second store_messages call must reuse the same connection without reconnecting."""
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = MagicMock()
        mock_pyodbc.connect.return_value = mock_conn

        self.client.store_messages([_make_record()])
        self.client.store_messages([_make_record()])

        # pyodbc.connect should only have been called once
        mock_pyodbc.connect.assert_called_once()

    @patch("message_store_service.db_client.pyodbc")
    def test_connection_is_recreated_after_error(self, mock_pyodbc: MagicMock) -> None:
        """After a DB error the stale connection is discarded; the next call opens a fresh one."""
        # First call: executemany blows up
        mock_conn_1 = MagicMock()
        bad_cursor = MagicMock()
        bad_cursor.executemany.side_effect = Exception("DB error")
        mock_conn_1.cursor.return_value = bad_cursor

        # Second call: works fine
        mock_conn_2 = MagicMock()
        mock_conn_2.cursor.return_value = MagicMock()

        mock_pyodbc.connect.side_effect = [mock_conn_1, mock_conn_2]

        with self.assertRaises(Exception):
            self.client.store_messages([_make_record()])

        # Connection 1 should have been discarded
        mock_conn_1.close.assert_called_once()

        # Second call should succeed and use a brand-new connection
        self.client.store_messages([_make_record()])
        self.assertEqual(mock_pyodbc.connect.call_count, 2)
        mock_conn_2.commit.assert_called_once()

    @patch("message_store_service.db_client.pyodbc")
    def test_explicit_close_releases_connection(self, mock_pyodbc: MagicMock) -> None:
        """Calling close() must close and discard the cached connection."""
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = MagicMock()
        mock_pyodbc.connect.return_value = mock_conn

        self.client.store_messages([_make_record()])
        self.client.close()

        mock_conn.close.assert_called_once()
        # A subsequent store_messages call must reconnect
        mock_pyodbc.connect.reset_mock()
        mock_conn_2 = MagicMock()
        mock_conn_2.cursor.return_value = MagicMock()
        mock_pyodbc.connect.return_value = mock_conn_2

        self.client.store_messages([_make_record()])
        mock_pyodbc.connect.assert_called_once()

    # ------------------------------------------------------------------
    # Empty batch
    # ------------------------------------------------------------------

    @patch("message_store_service.db_client.pyodbc")
    def test_store_messages_skips_insert_on_empty_list(self, mock_pyodbc: MagicMock) -> None:
        """An empty message list should not open a connection or execute SQL."""
        self.client.store_messages([])
        mock_pyodbc.connect.assert_not_called()

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    @patch("message_store_service.db_client.pyodbc")
    def test_store_messages_rolls_back_on_executemany_error(self, mock_pyodbc: MagicMock) -> None:
        """If executemany raises, the transaction must be rolled back, the error re-raised,
        and the stale connection discarded so the next call reconnects."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.executemany.side_effect = Exception("DB error")
        mock_conn.cursor.return_value = mock_cursor
        mock_pyodbc.connect.return_value = mock_conn

        with self.assertRaises(Exception) as ctx:
            self.client.store_messages([_make_record()])

        self.assertIn("DB error", str(ctx.exception))
        mock_conn.rollback.assert_called_once()
        mock_conn.commit.assert_not_called()
        # Connection must be closed so the next call reconnects cleanly.
        mock_conn.close.assert_called_once()

    @patch("message_store_service.db_client.pyodbc")
    def test_store_messages_closes_connection_on_commit_error(self, mock_pyodbc: MagicMock) -> None:
        """If commit raises, the connection must be rolled back and discarded."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.commit.side_effect = Exception("Commit failed")
        mock_pyodbc.connect.return_value = mock_conn

        with self.assertRaises(Exception):
            self.client.store_messages([_make_record()])

        mock_conn.rollback.assert_called_once()
        mock_conn.close.assert_called_once()

    @patch("message_store_service.db_client.pyodbc")
    def test_store_messages_raises_on_connection_failure(self, mock_pyodbc: MagicMock) -> None:
        """If pyodbc.connect itself fails, the error propagates."""
        mock_pyodbc.connect.side_effect = Exception("Connection refused")

        with self.assertRaises(Exception) as ctx:
            self.client.store_messages([_make_record()])

        self.assertIn("Connection refused", str(ctx.exception))

    # ------------------------------------------------------------------
    # Auth input validation
    # ------------------------------------------------------------------

    def test_raises_value_error_for_asymmetric_auth_inputs(self) -> None:
        """DatabaseClient must raise ValueError whenever exactly one of sql_username/sql_password is provided."""
        # Each tuple: (sql_username, sql_password, expected_missing_field_in_error)
        invalid_cases = [
            (None,  "secret", "sql_username", "password set, username is None"),
            ("",    "secret", "sql_username", "password set, username is empty string"),
            ("sa",  None,     "sql_password", "username set, password is None"),
            ("sa",  "",       "sql_password", "username set, password is empty string"),
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
        """DatabaseClient must construct without error for symmetric auth inputs.
        Both credentials provided (password auth) and neither provided (Managed Identity) are valid.
        """
        valid_cases = [
            ("sa",  "secret", "both username and password provided"),
            (None,  None,     "neither username nor password provided (Managed Identity)"),
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

    @patch("message_store_service.db_client.pyodbc")
    def test_connect_uses_password_auth_when_password_set(self, mock_pyodbc: MagicMock) -> None:
        """When sql_username and sql_password are both provided, connect should use UID/PWD."""
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = MagicMock()
        mock_pyodbc.connect.return_value = mock_conn

        self.client.store_messages([_make_record()])

        conn_str = mock_pyodbc.connect.call_args[0][0]
        self.assertIn("UID=sa", conn_str)
        self.assertIn("PWD=secret", conn_str)

    @patch("message_store_service.db_client.pyodbc")
    def test_connect_uses_managed_identity_system_assigned_when_no_password(self, mock_pyodbc: MagicMock) -> None:
        """When both sql_username and sql_password are None, uses system-assigned MI (no UID)."""
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

        client.store_messages([_make_record()])

        conn_str = mock_pyodbc.connect.call_args[0][0]
        self.assertIn("Authentication=ActiveDirectoryMsi", conn_str)
        # No UID should be present for system-assigned identity
        self.assertNotIn("UID=", conn_str)
        self.assertNotIn("PWD=", conn_str)

    @patch("message_store_service.db_client.pyodbc")
    def test_connect_uses_managed_identity_user_assigned_when_client_id_provided(
        self, mock_pyodbc: MagicMock
    ) -> None:
        """When managed_identity_client_id is set, UID is the client ID for user-assigned MI selection."""
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

        client.store_messages([_make_record()])

        conn_str = mock_pyodbc.connect.call_args[0][0]
        self.assertIn("Authentication=ActiveDirectoryMsi", conn_str)
        self.assertIn("UID=my-mi-client-id", conn_str)
        self.assertNotIn("PWD=", conn_str)

    # ------------------------------------------------------------------
    # Row content correctness
    # ------------------------------------------------------------------

    @patch("message_store_service.db_client.datetime")
    @patch("message_store_service.db_client.pyodbc")
    def test_store_messages_row_tuple_matches_column_order(
        self, mock_pyodbc: MagicMock, mock_dt: MagicMock
    ) -> None:
        """Verify the tuple order matches the INSERT column order and stored_at is injected by db_client."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pyodbc.connect.return_value = mock_conn

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
        )

        self.client.store_messages([record])

        row = mock_cursor.executemany.call_args[0][1][0]
        # Column order: ReceivedAt, StoredAt, CorrelationId, SourceSystem,
        #               ProcessingComponent, TargetSystem, RawPayload, XmlPayload
        self.assertEqual(row, (received_at, fixed_stored_at, "cid", "src", "comp", "tgt", "raw", "<xml/>"))

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def test_context_manager(self) -> None:
        """Verify DatabaseClient can be used as a context manager."""
        with self.client as client:
            self.assertIsInstance(client, DatabaseClient)

    @patch("message_store_service.db_client.pyodbc")
    def test_context_manager_closes_connection_on_exit(self, mock_pyodbc: MagicMock) -> None:
        """__exit__ must close and discard the persistent connection."""
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = MagicMock()
        mock_pyodbc.connect.return_value = mock_conn

        with self.client:
            self.client.store_messages([_make_record()])
            # Connection open, not yet closed
            mock_conn.close.assert_not_called()

        # Connection should be closed once the context exits
        mock_conn.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()

