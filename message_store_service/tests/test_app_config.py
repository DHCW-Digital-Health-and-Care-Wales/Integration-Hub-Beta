import unittest
from typing import Optional
from unittest.mock import MagicMock, patch

from message_store_service.app_config import AppConfig


class TestAppConfig(unittest.TestCase):
    @patch("message_store_service.app_config.os.getenv")
    def test_read_env_config_returns_config(self, mock_getenv: MagicMock) -> None:
        def getenv_side_effect(name: str) -> Optional[str]:
            values = {
                "SERVICE_BUS_CONNECTION_STRING": "conn_str",
                "INGRESS_QUEUE_NAME": "queue",
                "SERVICE_BUS_NAMESPACE": "namespace",
                "MICROSERVICE_ID": "microservice_id",
                "HEALTH_CHECK_HOST": "localhost",
                "HEALTH_CHECK_PORT": "9000",
                "PG_HOST": "postgres",
                "PG_PORT": "5433",
                "PG_DATABASE": "integrationhub",
                "PG_USER": "inthub",
                "POSTGRES_PASSWORD": "secret",  # nosec B105 — test fixture, not real password
                "PG_SSLMODE": "disable",
                "MANAGED_IDENTITY_CLIENT_ID": "my-mi-client-id",
            }
            return values.get(name)

        mock_getenv.side_effect = getenv_side_effect

        config = AppConfig.read_env_config()
        self.assertEqual(config.connection_string, "conn_str")
        self.assertEqual(config.ingress_queue_name, "queue")
        self.assertEqual(config.service_bus_namespace, "namespace")
        self.assertEqual(config.microservice_id, "microservice_id")
        self.assertEqual(config.health_check_hostname, "localhost")
        self.assertEqual(config.health_check_port, 9000)
        # PostgreSQL config — explicit values from env override the defaults
        self.assertEqual(config.pg_host, "postgres")
        self.assertEqual(config.pg_port, 5433)
        self.assertEqual(config.pg_database, "integrationhub")
        self.assertEqual(config.pg_user, "inthub")
        self.assertEqual(config.pg_password, "secret")
        self.assertEqual(config.pg_sslmode, "disable")
        self.assertEqual(config.managed_identity_client_id, "my-mi-client-id")

    @patch("message_store_service.app_config.os.getenv")
    def test_read_env_config_uses_secure_defaults_when_optional_pg_vars_absent(self, mock_getenv: MagicMock) -> None:
        """TLS must be required and the standard port assumed when the optional vars are unset."""

        def getenv_side_effect(name: str) -> Optional[str]:
            values = {
                "SERVICE_BUS_CONNECTION_STRING": "conn_str",
                "INGRESS_QUEUE_NAME": "queue",
                "MICROSERVICE_ID": "microservice_id",
                "PG_HOST": "myserver.postgres.database.azure.com",
                "PG_DATABASE": "integrationhub",
                "PG_USER": "message-store-identity",
            }
            return values.get(name)

        mock_getenv.side_effect = getenv_side_effect

        config = AppConfig.read_env_config()
        self.assertEqual(config.pg_sslmode, "require")
        self.assertEqual(config.pg_port, 5432)

    @patch("message_store_service.app_config.os.getenv")
    def test_read_env_config_with_minimal_required_vars(self, mock_getenv: MagicMock) -> None:
        """Test with only required environment variables."""

        def getenv_side_effect(name: str) -> Optional[str]:
            values = {
                "SERVICE_BUS_CONNECTION_STRING": "conn_str",
                "INGRESS_QUEUE_NAME": "queue",
                "MICROSERVICE_ID": "microservice_id",
                "PG_HOST": "myserver.postgres.database.azure.com",
                "PG_DATABASE": "integrationhub",
                "PG_USER": "message-store-identity",
            }
            return values.get(name)

        mock_getenv.side_effect = getenv_side_effect

        config = AppConfig.read_env_config()
        self.assertEqual(config.connection_string, "conn_str")
        self.assertEqual(config.ingress_queue_name, "queue")
        self.assertEqual(config.microservice_id, "microservice_id")
        self.assertIsNone(config.health_check_hostname)
        self.assertIsNone(config.health_check_port)
        self.assertEqual(config.pg_host, "myserver.postgres.database.azure.com")
        self.assertEqual(config.pg_database, "integrationhub")
        self.assertEqual(config.pg_user, "message-store-identity")
        # No password means Managed Identity auth.
        self.assertIsNone(config.pg_password)
        self.assertEqual(config.pg_sslmode, "require")
        self.assertIsNone(config.managed_identity_client_id)

    @patch("message_store_service.app_config.os.getenv")
    def test_read_env_config_missing_required_env_var_raises_error(self, mock_getenv: MagicMock) -> None:
        mock_getenv.return_value = None
        with self.assertRaises(RuntimeError) as context:
            AppConfig.read_env_config()
        self.assertIn("Missing required configuration", str(context.exception))

    @patch("message_store_service.app_config.os.getenv")
    def test_read_env_config_missing_pg_user_raises_error(self, mock_getenv: MagicMock) -> None:
        """PG_USER is required even under Managed Identity auth — PostgreSQL always needs a role name."""

        def getenv_side_effect(name: str) -> Optional[str]:
            values = {
                "SERVICE_BUS_CONNECTION_STRING": "conn_str",
                "INGRESS_QUEUE_NAME": "queue",
                "MICROSERVICE_ID": "microservice_id",
                "PG_HOST": "myserver.postgres.database.azure.com",
                "PG_DATABASE": "integrationhub",
            }
            return values.get(name)

        mock_getenv.side_effect = getenv_side_effect

        with self.assertRaises(RuntimeError) as context:
            AppConfig.read_env_config()
        self.assertIn("PG_USER", str(context.exception))


if __name__ == "__main__":
    unittest.main()
