import unittest
from unittest.mock import MagicMock, patch

import pyodbc

from db_sender.app_config import AppConfig
from db_sender.db_client import (
    DatabaseClient,
    FatalDatabaseError,
    TransientDatabaseError,
    sanitize_error_message,
)

TEST_CREDENTIAL = "dummy_auth_token"


class TestDatabaseClient(unittest.TestCase):
    def _create_config(
        self,
        db_username: str | None = "dbuser",
        db_password: str | None = None,
        managed_identity_client_id: str | None = None,
    ) -> AppConfig:
        effective_pwd = db_password if db_password is not None else (TEST_CREDENTIAL if db_username else None)
        return AppConfig(
            connection_string="Endpoint=sb://localhost;",
            service_bus_namespace=None,
            ingress_topic_name="test-topic",
            ingress_subscription_name="test-sub",
            ingress_session_id="test-session",
            db_server="sql-server-host",
            db_port=1433,
            db_name="DRS",
            db_stored_procedure="dbo.prQueueMessage",
            db_username=db_username,
            db_password=effective_pwd,
            db_encrypt="Yes",
            db_trust_server_certificate="No",
            db_connection_timeout=30,
            db_command_timeout=60,
            managed_identity_client_id=managed_identity_client_id,
            workflow_id="risp-to-wrrs",
            microservice_id="wrrs_stmsg_dbsender",
            health_board="SHARED",
            peer_service="WRRS",
            health_check_hostname="127.0.0.1",
            health_check_port=9000,
            log_level="INFO",
            default_is_priority=0,
            max_batch_size=10,
        )

    def test_connection_string_password_auth(self) -> None:
        # Passwords and usernames with semicolons and closing braces must be brace-quoted
        # with embedded closing braces doubled to prevent ODBC connection string parsing issues.
        config = self._create_config(
            db_username="my;user}name",
            db_password="secret;pass}word}",  # nosec B106
        )
        client = DatabaseClient(config)
        conn_str = client._build_connection_string()
        self.assertIn("SERVER=sql-server-host,1433", conn_str)
        self.assertIn("DATABASE=DRS", conn_str)
        self.assertIn("UID={my;user}}name}", conn_str)
        self.assertIn("PWD={secret;pass}}word}}}", conn_str)
        self.assertNotIn("Authentication=ActiveDirectoryMsi", conn_str)
        # Timeout must not be in the connection string (it sets query timeout, not login timeout)
        self.assertNotIn("Timeout=", conn_str)

    def test_connection_string_password_auth_plain(self) -> None:
        config = self._create_config(db_username="myuser", db_password="plainpassword")  # nosec B106
        client = DatabaseClient(config)
        conn_str = client._build_connection_string()
        self.assertIn("UID={myuser}", conn_str)
        self.assertIn("PWD={plainpassword}", conn_str)

    def test_connection_string_managed_identity(self) -> None:
        config = self._create_config(
            db_username=None,
            db_password=None,
            managed_identity_client_id="11111111-2222-3333-4444-555555555555",
        )
        client = DatabaseClient(config)
        conn_str = client._build_connection_string()
        self.assertIn("Authentication=ActiveDirectoryMsi", conn_str)
        self.assertIn("UID=11111111-2222-3333-4444-555555555555", conn_str)
        self.assertNotIn("PWD=", conn_str)

    @patch("pyodbc.connect")
    def test_execute_stored_procedure_success(self, mock_connect: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        config = self._create_config()
        client = DatabaseClient(config)

        client.execute_stored_procedure("<XML>payload</XML>", is_priority=False)

        mock_connect.assert_called_once_with(
            client._build_connection_string(),
            autocommit=False,
            timeout=30,
        )
        mock_cursor.execute.assert_called_once_with("{CALL dbo.prQueueMessage (?, ?)}", ("<XML>payload</XML>", 0))
        mock_conn.commit.assert_called_once()
        self.assertEqual(mock_conn.timeout, 60)

    @patch("pyodbc.connect")
    def test_execute_stored_procedure_priority_true(self, mock_connect: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        config = self._create_config()
        client = DatabaseClient(config)

        client.execute_stored_procedure("<XML>payload</XML>", is_priority=True)

        mock_cursor.execute.assert_called_once_with("{CALL dbo.prQueueMessage (?, ?)}", ("<XML>payload</XML>", 1))

    @patch("pyodbc.connect")
    def test_execute_stored_procedure_transient_error(self, mock_connect: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        # Simulate timeout error
        mock_cursor.execute.side_effect = pyodbc.OperationalError("HYT00", "[HYT00] [Microsoft] Query timeout expired")

        config = self._create_config()
        client = DatabaseClient(config)

        with self.assertRaises(TransientDatabaseError) as ctx:
            client.execute_stored_procedure("<XML>test</XML>")

        self.assertEqual(ctx.exception.sql_state, "HYT00")
        self.assertIsNone(client._connection)

    @patch("pyodbc.connect")
    def test_execute_stored_procedure_deadlock_error(self, mock_connect: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        # Simulate SQL Server deadlock victim (1205)
        mock_cursor.execute.side_effect = pyodbc.Error(
            "40001", "[40001] [Microsoft][SQL Server] 1205 Transaction was deadlocked"
        )

        config = self._create_config()
        client = DatabaseClient(config)

        with self.assertRaises(TransientDatabaseError) as ctx:
            client.execute_stored_procedure("<XML>test</XML>")

        self.assertEqual(ctx.exception.sql_state, "40001")

    @patch("pyodbc.connect")
    def test_execute_stored_procedure_fatal_error(self, mock_connect: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        # Simulate stored procedure not found (2812)
        mock_cursor.execute.side_effect = pyodbc.ProgrammingError(
            "42000",
            "[42000] [Microsoft][SQL Server] 2812 Could not find stored procedure 'dbo.prQueueMessage'",
        )

        config = self._create_config()
        client = DatabaseClient(config)

        with self.assertRaises(FatalDatabaseError) as ctx:
            client.execute_stored_procedure("<XML>test</XML>")

        self.assertEqual(ctx.exception.sql_state, "42000")
        self.assertIn("Could not find stored procedure", ctx.exception.error_message)

    def test_sanitize_error_message_conversion_failure(self) -> None:
        sentinel_patient_id = "9999999999"
        raw_msg = (
            f"[22018] [Microsoft][ODBC Driver 18 for SQL Server][SQL Server]"
            f"Conversion failed when converting the varchar value '{sentinel_patient_id}' to data type int."
        )
        sanitized = sanitize_error_message(raw_msg)
        self.assertNotIn(sentinel_patient_id, sanitized)
        self.assertIn("converting the varchar value '***' to data type int.", sanitized)

    def test_sanitize_error_message_duplicate_key(self) -> None:
        sentinel_patient = "9999999999, DOE, 1980-01-01"
        raw_msg = (
            f"[23000] [Microsoft][ODBC Driver 18 for SQL Server][SQL Server]"
            f"Violation of PRIMARY KEY constraint 'PK_Msg'. Cannot insert duplicate key in object 'dbo.Messages'. "
            f"The duplicate key value is ({sentinel_patient})."
        )
        sanitized = sanitize_error_message(raw_msg)
        self.assertNotIn(sentinel_patient, sanitized)
        self.assertNotIn("DOE", sanitized)
        self.assertIn("The duplicate key value is (***).", sanitized)

    def test_sanitize_error_message_string_truncation(self) -> None:
        sentinel_payload = "<ADT_A39><PID><PID.5>PATIENT_SECRET_DATA</PID.5></PID></ADT_A39>"
        raw_msg = (
            f"[22001] [Microsoft][ODBC Driver 18 for SQL Server][SQL Server]"
            f"String or binary data would be truncated in table 'DRS.dbo.Messages', column 'Payload'. "
            f"Truncated value: '{sentinel_payload}'."
        )
        sanitized = sanitize_error_message(raw_msg)
        self.assertNotIn(sentinel_payload, sanitized)
        self.assertNotIn("PATIENT_SECRET_DATA", sanitized)
        self.assertIn("Truncated value: '***'.", sanitized)

    @patch("pyodbc.connect")
    def test_execute_stored_procedure_redacts_patient_data_on_conversion_error(
        self, mock_connect: MagicMock
    ) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        sentinel_nhs_no = "9876543210"
        err_text = (
            f"[22018] [Microsoft][SQL Server] 245 Conversion failed when converting "
            f"the varchar value '{sentinel_nhs_no}' to data type int."
        )
        mock_cursor.execute.side_effect = pyodbc.ProgrammingError("22018", err_text)

        config = self._create_config()
        client = DatabaseClient(config)

        with self.assertRaises(FatalDatabaseError) as ctx:
            client.execute_stored_procedure("<XML>test</XML>")

        self.assertEqual(ctx.exception.sql_state, "22018")
        self.assertEqual(ctx.exception.error_code, 245)
        self.assertNotIn(sentinel_nhs_no, ctx.exception.error_message)
        self.assertNotIn(sentinel_nhs_no, str(ctx.exception))
        self.assertIn("converting the varchar value '***' to data type int", ctx.exception.error_message)


if __name__ == "__main__":
    unittest.main()
