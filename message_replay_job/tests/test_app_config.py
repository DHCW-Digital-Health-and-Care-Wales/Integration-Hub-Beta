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
                "MSSQL_SA_PASSWORD": "secret",  # nosec B105 — test fixture, not real password
                "SQL_ENCRYPT": "No",
                "SQL_TRUST_SERVER_CERTIFICATE": "Yes",
                "MANAGED_IDENTITY_CLIENT_ID": "my-mi-client-id",
                "REPLAY_BATCH_SIZE": "500",
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
        self.assertEqual(config.replay_batch_size, 500)

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

    @patch("message_replay_job.app_config.os.getenv")
    def test_replay_batch_size_defaults_when_absent(self, mock_getenv: MagicMock) -> None:
        """REPLAY_BATCH_SIZE absent or empty/whitespace should use the default value."""

        base_env = {
            "REPLAY_BATCH_ID": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "PRIORITY_QUEUE_NAME": "priority-queue",
            "SQL_SERVER": "localhost",
            "SQL_DATABASE": "IntegrationHub",
        }

        test_cases = [None, "", "   "]

        for batch_size_value in test_cases:
            with self.subTest(batch_size_value=batch_size_value):
                env = base_env.copy()
                if batch_size_value is not None:
                    env["REPLAY_BATCH_SIZE"] = batch_size_value

                mock_getenv.side_effect = env.get
                config = AppConfig.read_env_config()
                self.assertEqual(config.replay_batch_size, 100)

    @patch("message_replay_job.app_config.os.getenv")
    def test_replay_batch_size_parsed_when_valid(self, mock_getenv: MagicMock) -> None:
        """A valid positive integer string should be parsed into replay_batch_size."""

        def getenv_side_effect(name: str) -> Optional[str]:
            values = {
                "REPLAY_BATCH_ID": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "PRIORITY_QUEUE_NAME": "priority-queue",
                "SQL_SERVER": "localhost",
                "SQL_DATABASE": "IntegrationHub",
                "REPLAY_BATCH_SIZE": "250",
            }
            return values.get(name)

        mock_getenv.side_effect = getenv_side_effect

        config = AppConfig.read_env_config()
        self.assertEqual(config.replay_batch_size, 250)

    @patch("message_replay_job.app_config.os.getenv")
    def test_replay_batch_size_raises_on_invalid_value(self, mock_getenv: MagicMock) -> None:
        """Non-integer, zero, and negative values should all raise RuntimeError."""
        invalid_cases = ["abc", "-1", "0"]

        base_env = {
            "REPLAY_BATCH_ID": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "PRIORITY_QUEUE_NAME": "priority-queue",
            "SQL_SERVER": "localhost",
            "SQL_DATABASE": "IntegrationHub",
        }

        for invalid_value in invalid_cases:
            with self.subTest(invalid_value=invalid_value):
                mock_getenv.side_effect = lambda name, v=invalid_value: {
                    **base_env,
                    "REPLAY_BATCH_SIZE": v,
                }.get(name)
                with self.assertRaises(RuntimeError) as context:
                    AppConfig.read_env_config()
                self.assertIn("REPLAY_BATCH_SIZE", str(context.exception))


if __name__ == "__main__":
    unittest.main()
