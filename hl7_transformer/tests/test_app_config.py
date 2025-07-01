import unittest
from unittest.mock import patch
from hl7_transformer.app_config import AppConfig


class TestAppConfig(unittest.TestCase):
    @patch("hl7_transformer.app_config.os.getenv")
    def test_read_env_config_returns_config(self, mock_getenv):
        def getenv_side_effect(name):
            values = {
                "SERVICE_BUS_CONNECTION_STRING": "conn_str",
                "INGRESS_QUEUE_NAME": "queue",
                "EGRESS_QUEUE_NAME": "topic",
                "SERVICE_BUS_NAMESPACE": "namespace",
                "AUDIT_QUEUE_NAME": "audit_queue",
                "WORKFLOW_ID": "workflow_id",
                "MICROSERVICE_ID": "microservice_id",
            }
            return values.get(name)

        mock_getenv.side_effect = getenv_side_effect

        config = AppConfig.read_env_config()
        self.assertEqual(config.connection_string, "conn_str")
        self.assertEqual(config.ingress_queue_name, "queue")
        self.assertEqual(config.egress_queue_name, "topic")
        self.assertEqual(config.service_bus_namespace, "namespace")

    @patch("hl7_transformer.app_config.os.getenv")
    def test_read_env_config_missing_required_env_var_raises_error(self, mock_getenv):
        mock_getenv.return_value = None
        with self.assertRaises(RuntimeError) as context:
            AppConfig.read_env_config()
        self.assertIn("Missing required configuration", str(context.exception))


if __name__ == "__main__":
    unittest.main()
