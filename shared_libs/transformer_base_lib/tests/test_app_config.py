import unittest
from typing import Optional
from unittest.mock import MagicMock, patch

from transformer_base_lib.app_config import AppConfig


class TestAppConfig(unittest.TestCase):
    @patch("transformer_base_lib.app_config.os.getenv")
    def test_read_env_config_returns_config(self, mock_getenv: MagicMock) -> None:
        def getenv_side_effect(name: str) -> Optional[str]:
            values = {
                "SERVICE_BUS_CONNECTION_STRING": "conn_str",
                "INGRESS_QUEUE_NAME": "queue",
                "INGRESS_SESSION_ID": "session_id",
                "EGRESS_QUEUE_NAME": "topic",
                "SERVICE_BUS_NAMESPACE": "namespace",
                "AUDIT_QUEUE_NAME": "audit_queue",
                "WORKFLOW_ID": "workflow_id",
                "MICROSERVICE_ID": "microservice_id",
                "HEALTH_CHECK_HOST": "localhost",
                "HEALTH_CHECK_PORT": "8080",
            }
            return values.get(name)

        mock_getenv.side_effect = getenv_side_effect

        config = AppConfig.read_env_config()
        self.assertEqual(config.connection_string, "conn_str")
        self.assertEqual(config.ingress_queue_name, "queue")
        self.assertEqual(config.ingress_session_id, "session_id")
        self.assertEqual(config.egress_queue_name, "topic")
        self.assertEqual(config.service_bus_namespace, "namespace")
        self.assertEqual(config.audit_queue_name, "audit_queue")
        self.assertEqual(config.workflow_id, "workflow_id")
        self.assertEqual(config.microservice_id, "microservice_id")
        self.assertEqual(config.health_check_hostname, "localhost")
        self.assertEqual(config.health_check_port, 8080)

    @patch("transformer_base_lib.app_config.os.getenv")
    def test_read_env_config_missing_required_env_var_raises_error(self, mock_getenv: MagicMock) -> None:
        mock_getenv.return_value = None
        with self.assertRaises(RuntimeError) as context:
            AppConfig.read_env_config()
        self.assertIn("Missing required configuration", str(context.exception))


if __name__ == '__main__':
    unittest.main()