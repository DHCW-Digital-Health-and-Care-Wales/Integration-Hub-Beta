from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from db_sender_trrr.app_config import AppConfig
from db_sender_trrr.db_client import DatabaseClient, TransientDatabaseError


def _config() -> AppConfig:
    return AppConfig(
        connection_string="Endpoint=sb://localhost;",
        service_bus_namespace=None,
        ingress_topic_name="topic",
        ingress_subscription_name="sub",
        ingress_session_id="session",
        db_server="localhost",
        db_port=1433,
        db_name="Clinical_Results",
        db_stored_procedure="dbo.spProcessIdUpdate",
        db_username="sa",
        db_password="Password123!",  # nosec B106
        db_encrypt="No",
        db_trust_server_certificate="Yes",
        db_connection_timeout=30,
        db_command_timeout=60,
        managed_identity_client_id=None,
        workflow_id="cav-pms-to-trrr",
        microservice_id="db_sender_trrr_cav",
        health_board="CAV",
        peer_service="TRRR",
        health_check_hostname=None,
        health_check_port=None,
        log_level="INFO",
        default_is_priority=0,
        max_batch_size=10,
    )


class TestDatabaseClient(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = MagicMock()
        self.cursor = MagicMock()
        self.connection.cursor.return_value.__enter__.return_value = self.cursor

    @patch("db_sender_trrr.db_client.pyodbc.connect")
    def test_successful_merge_commits_transaction_before_return(self, mock_connect: MagicMock) -> None:
        mock_connect.return_value = self.connection
        client = DatabaseClient(_config())

        client.execute_identifier_update(
            {
                "OldIdentifier": "U692047",
                "OldIdentifierAssigningAuthority": "140",
                "NewIdentifier": "U363137",
                "NewIdentifierAssigningAuthority": "140",
            }
        )

        self.cursor.execute.assert_called_once_with(
            "{CALL dbo.spProcessIdUpdate (?, ?, ?, ?)}",
            ("U692047", "140", "U363137", "140"),
        )
        self.connection.commit.assert_called_once()
        self.connection.rollback.assert_not_called()

    @patch("db_sender_trrr.db_client.pyodbc.connect")
    def test_successful_nhs_update_commits_transaction_before_return(self, mock_connect: MagicMock) -> None:
        mock_connect.return_value = self.connection
        client = DatabaseClient(_config())

        client.execute_identifier_update(
            {
                "LIMSIdentifier": "ABC123",
                "NewIdentifier": "9876543210",
                "NewIdentifierAssigningAuthority": "NHS",
            }
        )

        self.cursor.execute.assert_called_once_with(
            "{CALL dbo.spProcessIdUpdate (?, ?, ?)}",
            ("ABC123", "9876543210", "NHS"),
        )
        self.connection.commit.assert_called_once()

    @patch("db_sender_trrr.db_client.pyodbc.connect")
    def test_generic_database_failure_rolls_back_and_closes(self, mock_connect: MagicMock) -> None:
        mock_connect.return_value = self.connection
        self.cursor.execute.side_effect = RuntimeError("connection failure")
        client = DatabaseClient(_config())

        with self.assertRaises(TransientDatabaseError):
            client.execute_identifier_update(
                {
                    "OldIdentifier": "U692047",
                    "OldIdentifierAssigningAuthority": "140",
                    "NewIdentifier": "U363137",
                    "NewIdentifierAssigningAuthority": "140",
                }
            )

        self.connection.rollback.assert_called_once()
        self.connection.close.assert_called_once()
        self.connection.commit.assert_not_called()

    def test_close_rolls_back_active_transaction(self) -> None:
        client = DatabaseClient(_config())
        client._connection = self.connection

        client.close()

        self.connection.rollback.assert_called_once()
        self.connection.close.assert_called_once()
        self.assertIsNone(client._connection)


if __name__ == "__main__":
    unittest.main()
