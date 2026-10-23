import unittest
from unittest.mock import MagicMock, patch

import pyodbc

from db_sender.app_config import AppConfig
from db_sender.db_client import (
    DatabaseClient,
    FatalDatabaseError,
    TransientDatabaseError,
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
            microservice_id="wrrs_db_sender",
            health_board="SHARED",
            peer_service="WRRS",
            health_check_hostname="127.0.0.1",
            health_check_port=9000,
            log_level="INFO",
            default_is_priority=0,
            max_batch_size=10,
        )

    def test_connection_string_password_auth(self) -> None:
        config = self._create_config(db_username="myuser", db_password=TEST_CREDENTIAL)
        client = DatabaseClient(config)
        conn_str = client._build_connection_string()
        self.assertIn("SERVER=sql-server-host,1433", conn_str)
        self.assertIn("DATABASE=DRS", conn_str)
        self.assertIn("UID=myuser", conn_str)
        self.assertIn(f"PWD={TEST_CREDENTIAL}", conn_str)
        self.assertNotIn("Authentication=ActiveDirectoryMsi", conn_str)

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

        mock_cursor.execute.assert_called_once_with("{CALL dbo.prQueueMessage (?, ?)}", ("<XML>payload</XML>", 0))
        mock_conn.commit.assert_called_once()
        self.assertEqual(mock_cursor.timeout, 60)

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


if __name__ == "__main__":
    unittest.main()
