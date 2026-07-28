import unittest
from typing import Optional
from unittest.mock import MagicMock, patch

from message_replay_job.app_config import AppConfig

BATCH_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

# The minimum set of variables every test needs; individual tests layer extras on top.
MINIMAL_ENV = {
    "REPLAY_BATCH_ID": BATCH_ID,
    "PRIORITY_QUEUE_NAME": "priority-queue",
    "PG_HOST": "myserver.postgres.database.azure.com",
    "PG_DATABASE": "integrationhub",
    "PG_USER": "replay-identity",
}


class TestAppConfig(unittest.TestCase):
    @patch("message_replay_job.app_config.os.getenv")
    def test_read_env_config_returns_config(self, mock_getenv: MagicMock) -> None:
        def getenv_side_effect(name: str) -> Optional[str]:
            values = {
                "REPLAY_BATCH_ID": BATCH_ID,
                "SERVICE_BUS_CONNECTION_STRING": "conn_str",
                "SERVICE_BUS_NAMESPACE": "namespace",
                "PRIORITY_QUEUE_NAME": "priority-queue",
                "PG_HOST": "postgres",
                "PG_PORT": "5433",
                "PG_DATABASE": "integrationhub",
                "PG_USER": "inthub",
                "POSTGRES_PASSWORD": "secret",  # nosec B105 — test fixture, not real password
                "PG_SSLMODE": "disable",
                "MANAGED_IDENTITY_CLIENT_ID": "my-mi-client-id",
                "REPLAY_BATCH_SIZE": "500",
            }
            return values.get(name)

        mock_getenv.side_effect = getenv_side_effect

        config = AppConfig.read_env_config()
        self.assertEqual(config.replay_batch_id, BATCH_ID)
        self.assertEqual(config.connection_string, "conn_str")
        self.assertEqual(config.service_bus_namespace, "namespace")
        self.assertEqual(config.priority_queue_name, "priority-queue")
        self.assertEqual(config.pg_host, "postgres")
        self.assertEqual(config.pg_port, 5433)
        self.assertEqual(config.pg_database, "integrationhub")
        self.assertEqual(config.pg_user, "inthub")
        self.assertEqual(config.pg_password, "secret")
        self.assertEqual(config.pg_sslmode, "disable")
        self.assertEqual(config.managed_identity_client_id, "my-mi-client-id")
        self.assertEqual(config.replay_batch_size, 500)

    @patch("message_replay_job.app_config.os.getenv")
    def test_read_env_config_uses_secure_defaults_when_optional_pg_vars_absent(self, mock_getenv: MagicMock) -> None:
        """TLS must be required and the standard port assumed when the optional vars are unset."""
        mock_getenv.side_effect = MINIMAL_ENV.get

        config = AppConfig.read_env_config()
        self.assertEqual(config.pg_sslmode, "require")
        self.assertEqual(config.pg_port, 5432)

    @patch("message_replay_job.app_config.os.getenv")
    def test_read_env_config_with_minimal_required_vars(self, mock_getenv: MagicMock) -> None:
        """Test with only required environment variables."""
        mock_getenv.side_effect = MINIMAL_ENV.get

        config = AppConfig.read_env_config()
        self.assertEqual(config.replay_batch_id, BATCH_ID)
        self.assertEqual(config.priority_queue_name, "priority-queue")
        self.assertIsNone(config.connection_string)
        self.assertIsNone(config.service_bus_namespace)
        self.assertEqual(config.pg_user, "replay-identity")
        # No password means Managed Identity auth.
        self.assertIsNone(config.pg_password)
        self.assertIsNone(config.managed_identity_client_id)

    @patch("message_replay_job.app_config.os.getenv")
    def test_read_env_config_missing_required_env_var_raises_error(self, mock_getenv: MagicMock) -> None:
        mock_getenv.return_value = None
        with self.assertRaises(RuntimeError) as context:
            AppConfig.read_env_config()
        self.assertIn("Missing required configuration", str(context.exception))

    @patch("message_replay_job.app_config.os.getenv")
    def test_read_env_config_missing_pg_user_raises_error(self, mock_getenv: MagicMock) -> None:
        """PG_USER is required even under Managed Identity auth — PostgreSQL always needs a role name."""
        env = {k: v for k, v in MINIMAL_ENV.items() if k != "PG_USER"}
        mock_getenv.side_effect = env.get

        with self.assertRaises(RuntimeError) as context:
            AppConfig.read_env_config()
        self.assertIn("PG_USER", str(context.exception))

    @patch("message_replay_job.app_config.os.getenv")
    def test_read_env_config_invalid_uuid_raises_error(self, mock_getenv: MagicMock) -> None:
        env = {**MINIMAL_ENV, "REPLAY_BATCH_ID": "not-a-valid-uuid"}
        mock_getenv.side_effect = env.get

        with self.assertRaises(RuntimeError) as context:
            AppConfig.read_env_config()
        self.assertIn("not a valid UUID", str(context.exception))

    @patch("message_replay_job.app_config.os.getenv")
    def test_read_env_config_valid_uuid_accepted(self, mock_getenv: MagicMock) -> None:
        """Various valid UUID formats should be accepted."""
        env = {**MINIMAL_ENV, "REPLAY_BATCH_ID": "00000000-0000-0000-0000-000000000001"}
        mock_getenv.side_effect = env.get

        config = AppConfig.read_env_config()
        self.assertEqual(config.replay_batch_id, "00000000-0000-0000-0000-000000000001")

    @patch("message_replay_job.app_config.os.getenv")
    def test_replay_batch_size_defaults_when_absent(self, mock_getenv: MagicMock) -> None:
        """REPLAY_BATCH_SIZE absent or empty/whitespace should use the default value."""
        test_cases = [None, "", "   "]

        for batch_size_value in test_cases:
            with self.subTest(batch_size_value=batch_size_value):
                env = MINIMAL_ENV.copy()
                if batch_size_value is not None:
                    env["REPLAY_BATCH_SIZE"] = batch_size_value

                mock_getenv.side_effect = env.get
                config = AppConfig.read_env_config()
                self.assertEqual(config.replay_batch_size, 100)

    @patch("message_replay_job.app_config.os.getenv")
    def test_replay_batch_size_parsed_when_valid(self, mock_getenv: MagicMock) -> None:
        """A valid positive integer string should be parsed into replay_batch_size."""
        env = {**MINIMAL_ENV, "REPLAY_BATCH_SIZE": "250"}
        mock_getenv.side_effect = env.get

        config = AppConfig.read_env_config()
        self.assertEqual(config.replay_batch_size, 250)

    @patch("message_replay_job.app_config.os.getenv")
    def test_replay_batch_size_raises_on_invalid_value(self, mock_getenv: MagicMock) -> None:
        """Non-integer, zero, and negative values should all raise RuntimeError."""
        invalid_cases = ["abc", "-1", "0"]

        for invalid_value in invalid_cases:
            with self.subTest(invalid_value=invalid_value):
                mock_getenv.side_effect = lambda name, v=invalid_value: {
                    **MINIMAL_ENV,
                    "REPLAY_BATCH_SIZE": v,
                }.get(name)
                with self.assertRaises(RuntimeError) as context:
                    AppConfig.read_env_config()
                self.assertIn("REPLAY_BATCH_SIZE", str(context.exception))


if __name__ == "__main__":
    unittest.main()
