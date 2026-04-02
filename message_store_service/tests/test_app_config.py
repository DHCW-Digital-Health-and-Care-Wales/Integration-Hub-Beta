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
                "SQL_SERVER": "localhost,1433",
                "SQL_DATABASE": "IntegrationHub",
                "SQL_USERNAME": "sa",
                "MSSQL_SA_PASSWORD": "secret",  # nosec B105 — test fixture, not real password
                "SQL_ENCRYPT": "No",
                "SQL_TRUST_SERVER_CERTIFICATE": "Yes",
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
        # SQL config — explicit values from env override the defaults
        self.assertEqual(config.sql_server, "localhost,1433")
        self.assertEqual(config.sql_database, "IntegrationHub")
        self.assertEqual(config.sql_username, "sa")
        self.assertEqual(config.sql_password, "secret")
        self.assertEqual(config.sql_encrypt, "No")
        self.assertEqual(config.sql_trust_server_certificate, "Yes")
        self.assertEqual(config.managed_identity_client_id, "my-mi-client-id")

    @patch("message_store_service.app_config.os.getenv")
    def test_read_env_config_uses_secure_defaults_when_sql_tls_vars_absent(
        self, mock_getenv: MagicMock
    ) -> None:
        def getenv_side_effect(name: str) -> Optional[str]:
            values = {
                "SERVICE_BUS_CONNECTION_STRING": "conn_str",
                "INGRESS_QUEUE_NAME": "queue",
                "MICROSERVICE_ID": "microservice_id",
                "SQL_SERVER": "myserver.database.windows.net",
                "SQL_DATABASE": "IntegrationHub",
            }
            return values.get(name)

        mock_getenv.side_effect = getenv_side_effect

        config = AppConfig.read_env_config()
        self.assertEqual(config.sql_encrypt, "Yes")
        self.assertEqual(config.sql_trust_server_certificate, "No")

    @patch("message_store_service.app_config.os.getenv")
    def test_read_env_config_with_minimal_required_vars(self, mock_getenv: MagicMock) -> None:
        """Test with only required environment variables."""
        def getenv_side_effect(name: str) -> Optional[str]:
            values = {
                "SERVICE_BUS_CONNECTION_STRING": "conn_str",
                "INGRESS_QUEUE_NAME": "queue",
                "MICROSERVICE_ID": "microservice_id",
                "SQL_SERVER": "myserver.database.windows.net",
                "SQL_DATABASE": "IntegrationHub",
            }
            return values.get(name)

        mock_getenv.side_effect = getenv_side_effect

        config = AppConfig.read_env_config()
        self.assertEqual(config.connection_string, "conn_str")
        self.assertEqual(config.ingress_queue_name, "queue")
        self.assertEqual(config.microservice_id, "microservice_id")
        self.assertIsNone(config.health_check_hostname)
        self.assertIsNone(config.health_check_port)
        self.assertEqual(config.sql_server, "myserver.database.windows.net")
        self.assertEqual(config.sql_database, "IntegrationHub")
        self.assertIsNone(config.sql_username)
        self.assertIsNone(config.sql_password)
        self.assertEqual(config.sql_encrypt, "Yes")
        self.assertEqual(config.sql_trust_server_certificate, "No")
        self.assertIsNone(config.managed_identity_client_id)

    @patch("message_store_service.app_config.os.getenv")
    def test_read_env_config_missing_required_env_var_raises_error(self, mock_getenv: MagicMock) -> None:
        mock_getenv.return_value = None
        with self.assertRaises(RuntimeError) as context:
            AppConfig.read_env_config()
        self.assertIn("Missing required configuration", str(context.exception))


if __name__ == "__main__":
    unittest.main()
