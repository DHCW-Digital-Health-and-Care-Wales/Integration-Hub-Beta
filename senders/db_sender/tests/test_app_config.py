import os
import unittest
from unittest.mock import patch

from db_sender.app_config import AppConfig


class TestAppConfig(unittest.TestCase):
    def setUp(self) -> None:
        self.valid_env = {
            "INGRESS_TOPIC_NAME": "test-topic",
            "INGRESS_SUBSCRIPTION_NAME": "test-sub",
            "SERVICE_BUS_CONNECTION_STRING": "Endpoint=sb://localhost;",
            "DB_SERVER": "sqledge",
            "DB_PORT": "1433",
            "DB_NAME": "DRS",
            "DB_STORED_PROCEDURE": "dbo.prQueueMessage",
            "DB_USERNAME": "sa",
            "DB_PASSWORD": "Password123!",  # nosec B106
            "WORKFLOW_ID": "risp-to-wrrs",
            "MICROSERVICE_ID": "wrrs_db_sender",
        }

    def test_read_env_config_success(self) -> None:
        with patch.dict(os.environ, self.valid_env, clear=True):
            config = AppConfig.read_env_config()
            self.assertEqual(config.ingress_topic_name, "test-topic")
            self.assertEqual(config.ingress_subscription_name, "test-sub")
            self.assertEqual(config.db_server, "sqledge")
            self.assertEqual(config.db_port, 1433)
            self.assertEqual(config.db_name, "DRS")
            self.assertEqual(config.db_stored_procedure, "dbo.prQueueMessage")
            self.assertEqual(config.db_username, "sa")
            self.assertEqual(config.db_password, "Password123!")
            self.assertEqual(config.default_is_priority, 0)
            self.assertEqual(config.max_batch_size, 10)

    def test_read_env_config_defaults(self) -> None:
        minimal_env = {
            "INGRESS_TOPIC_NAME": "test-topic",
            "INGRESS_SUBSCRIPTION_NAME": "test-sub",
        }
        with patch.dict(os.environ, minimal_env, clear=True):
            config = AppConfig.read_env_config()
            self.assertEqual(config.db_server, "localhost")
            self.assertEqual(config.db_port, 1433)
            self.assertEqual(config.db_name, "DRS")
            self.assertEqual(config.db_stored_procedure, "dbo.prQueueMessage")
            self.assertIsNone(config.db_username)
            self.assertIsNone(config.db_password)
            self.assertEqual(config.db_encrypt, "Yes")
            self.assertEqual(config.db_trust_server_certificate, "No")
            self.assertEqual(config.default_is_priority, 0)

    def test_read_env_config_mssql_sa_password_fallback(self) -> None:
        env_with_sa = {
            "INGRESS_TOPIC_NAME": "test-topic",
            "INGRESS_SUBSCRIPTION_NAME": "test-sub",
            "MSSQL_SA_PASSWORD": "SaPassword123!",  # nosec B106
        }
        with patch.dict(os.environ, env_with_sa, clear=True):
            config = AppConfig.read_env_config()
            self.assertEqual(config.db_username, "sa")
            self.assertEqual(config.db_password, "SaPassword123!")

    def test_read_env_config_missing_required(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                AppConfig.read_env_config()
            self.assertIn("Missing required configuration: INGRESS_TOPIC_NAME", str(ctx.exception))

    def test_read_env_config_invalid_int(self) -> None:
        bad_env = {
            **self.valid_env,
            "DB_PORT": "invalid-port",
        }
        with patch.dict(os.environ, bad_env, clear=True):
            with self.assertRaises(ValueError) as ctx:
                AppConfig.read_env_config()
            self.assertIn("Invalid integer value for configuration: DB_PORT", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
