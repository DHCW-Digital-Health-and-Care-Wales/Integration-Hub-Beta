import unittest
from typing import Optional
from unittest.mock import MagicMock, patch

from message_replay_job.app_config import AppConfig


class TestAppConfig(unittest.TestCase):
    @patch("message_replay_job.app_config.os.getenv")
    def test_read_env_config_returns_config(self, mock_getenv: MagicMock) -> None:
        def getenv_side_effect(name: str) -> Optional[str]:
            values = {
                "REPLAY_BATCH_ID": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "SERVICE_BUS_CONNECTION_STRING": "conn_str",
                "SERVICE_BUS_NAMESPACE": "namespace",
                "PRIORITY_QUEUE_NAME": "priority-queue",
                "SQL_SERVER": "localhost,1433",
                "SQL_DATABASE": "IntegrationHub",
                "SQL_USERNAME": "sa",
                "MSSQL_SA_PASSWORD": "secret",
                "SQL_ENCRYPT": "No",
                "SQL_TRUST_SERVER_CERTIFICATE": "Yes",
                "MANAGED_IDENTITY_CLIENT_ID": "my-mi-client-id",
            }
            return values.get(name)

        mock_getenv.side_effect = getenv_side_effect

        config = AppConfig.read_env_config()
        self.assertEqual(config.replay_batch_id, "a1b2c3d4-e5f6-7890-abcd-ef1234567890")
        self.assertEqual(config.connection_string, "conn_str")
        self.assertEqual(config.service_bus_namespace, "namespace")
        self.assertEqual(config.priority_queue_name, "priority-queue")
        self.assertEqual(config.sql_server, "localhost,1433")
        self.assertEqual(config.sql_database, "IntegrationHub")
        self.assertEqual(config.sql_username, "sa")
        self.assertEqual(config.sql_password, "secret")
        self.assertEqual(config.sql_encrypt, "No")
        self.assertEqual(config.sql_trust_server_certificate, "Yes")
        self.assertEqual(config.managed_identity_client_id, "my-mi-client-id")

    @patch("message_replay_job.app_config.os.getenv")
    def test_read_env_config_uses_secure_defaults_when_sql_tls_vars_absent(self, mock_getenv: MagicMock) -> None:
        def getenv_side_effect(name: str) -> Optional[str]:
            values = {
                "REPLAY_BATCH_ID": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "PRIORITY_QUEUE_NAME": "priority-queue",
                "SQL_SERVER": "myserver.database.windows.net",
                "SQL_DATABASE": "IntegrationHub",
            }
            return values.get(name)

        mock_getenv.side_effect = getenv_side_effect

        config = AppConfig.read_env_config()
        self.assertEqual(config.sql_encrypt, "Yes")
        self.assertEqual(config.sql_trust_server_certificate, "No")

    @patch("message_replay_job.app_config.os.getenv")
    def test_read_env_config_with_minimal_required_vars(self, mock_getenv: MagicMock) -> None:
        """Test with only required environment variables."""

        def getenv_side_effect(name: str) -> Optional[str]:
            values = {
                "REPLAY_BATCH_ID": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "PRIORITY_QUEUE_NAME": "priority-queue",
                "SQL_SERVER": "myserver.database.windows.net",
                "SQL_DATABASE": "IntegrationHub",
            }
            return values.get(name)

        mock_getenv.side_effect = getenv_side_effect

        config = AppConfig.read_env_config()
        self.assertEqual(config.replay_batch_id, "a1b2c3d4-e5f6-7890-abcd-ef1234567890")
        self.assertEqual(config.priority_queue_name, "priority-queue")
        self.assertIsNone(config.connection_string)
        self.assertIsNone(config.service_bus_namespace)
        self.assertIsNone(config.sql_username)
        self.assertIsNone(config.sql_password)
        self.assertIsNone(config.managed_identity_client_id)

    @patch("message_replay_job.app_config.os.getenv")
    def test_read_env_config_missing_required_env_var_raises_error(self, mock_getenv: MagicMock) -> None:
        mock_getenv.return_value = None
        with self.assertRaises(RuntimeError) as context:
            AppConfig.read_env_config()
        self.assertIn("Missing required configuration", str(context.exception))

    @patch("message_replay_job.app_config.os.getenv")
    def test_read_env_config_invalid_uuid_raises_error(self, mock_getenv: MagicMock) -> None:
        def getenv_side_effect(name: str) -> Optional[str]:
            values = {
                "REPLAY_BATCH_ID": "not-a-valid-uuid",
                "PRIORITY_QUEUE_NAME": "priority-queue",
                "SQL_SERVER": "localhost",
                "SQL_DATABASE": "IntegrationHub",
            }
            return values.get(name)

        mock_getenv.side_effect = getenv_side_effect

        with self.assertRaises(RuntimeError) as context:
            AppConfig.read_env_config()
        self.assertIn("not a valid UUID", str(context.exception))

    @patch("message_replay_job.app_config.os.getenv")
    def test_read_env_config_valid_uuid_accepted(self, mock_getenv: MagicMock) -> None:
        """Various valid UUID formats should be accepted."""

        def getenv_side_effect(name: str) -> Optional[str]:
            values = {
                "REPLAY_BATCH_ID": "00000000-0000-0000-0000-000000000001",
                "PRIORITY_QUEUE_NAME": "priority-queue",
                "SQL_SERVER": "localhost",
                "SQL_DATABASE": "IntegrationHub",
            }
            return values.get(name)

        mock_getenv.side_effect = getenv_side_effect

        config = AppConfig.read_env_config()
        self.assertEqual(config.replay_batch_id, "00000000-0000-0000-0000-000000000001")


if __name__ == "__main__":
    unittest.main()
