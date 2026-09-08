import unittest
from typing import Optional
from unittest.mock import MagicMock, patch

from transformer_base_lib.app_config import AppConfig, validate_ingress_config


class TestAppConfig(unittest.TestCase):
    @patch("transformer_base_lib.app_config.os.getenv")
    def test_read_env_config_returns_config(self, mock_getenv: MagicMock) -> None:
        def getenv_side_effect(name: str) -> Optional[str]:
            values = {
                "SERVICE_BUS_CONNECTION_STRING": "conn_str",
                "INGRESS_QUEUE_NAME": "queue",
                "INGRESS_SESSION_ID": "in_session_id",
                "EGRESS_QUEUE_NAME": "topic",
                "EGRESS_SESSION_ID": "out_session_id",
                "SERVICE_BUS_NAMESPACE": "namespace",
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
        self.assertEqual(config.ingress_session_id, "in_session_id")
        self.assertEqual(config.egress_queue_name, "topic")
        self.assertEqual(config.egress_session_id, "out_session_id")
        self.assertEqual(config.service_bus_namespace, "namespace")
        self.assertEqual(config.workflow_id, "workflow_id")
        self.assertEqual(config.microservice_id, "microservice_id")
        self.assertEqual(config.health_check_hostname, "localhost")
        self.assertEqual(config.health_check_port, 8080)

    @patch("transformer_base_lib.app_config.os.getenv")
    def test_read_env_config_missing_required_env_var_raises_error(
        self, mock_getenv: MagicMock
    ) -> None:
        mock_getenv.return_value = None
        with self.assertRaises(RuntimeError) as context:
            AppConfig.read_env_config()
        self.assertIn("Missing required configuration", str(context.exception))

    @patch("transformer_base_lib.app_config.os.getenv")
    def test_read_env_config_with_topic_ingress_returns_config(
        self, mock_getenv: MagicMock
    ) -> None:
        def getenv_side_effect(name: str) -> Optional[str]:
            values = {
                "INGRESS_TOPIC_NAME": "topic",
                "INGRESS_SUBSCRIPTION_NAME": "subscription",
                "INGRESS_SESSION_ID": "in_session_id",
                "EGRESS_QUEUE_NAME": "egress_queue",
                "WORKFLOW_ID": "workflow_id",
                "MICROSERVICE_ID": "microservice_id",
            }
            return values.get(name)

        mock_getenv.side_effect = getenv_side_effect

        config = AppConfig.read_env_config()
        self.assertIsNone(config.ingress_queue_name)
        self.assertEqual(config.ingress_topic_name, "topic")
        self.assertEqual(config.ingress_subscription_name, "subscription")

    def test_queue_and_topic_ingress_together_raises_error(self) -> None:
        with self.assertRaises(RuntimeError) as context:
            validate_ingress_config(
                ingress_queue_name="queue",
                ingress_topic_name="topic",
                ingress_subscription_name="subscription",
            )
        self.assertIn("cannot be set together", str(context.exception))

    def test_no_ingress_configured_raises_error(self) -> None:
        with self.assertRaises(RuntimeError) as context:
            validate_ingress_config(
                ingress_queue_name=None,
                ingress_topic_name=None,
                ingress_subscription_name=None,
            )
        self.assertIn("Missing required configuration", str(context.exception))

    def test_topic_without_subscription_raises_error(self) -> None:
        with self.assertRaises(RuntimeError) as context:
            validate_ingress_config(
                ingress_queue_name=None,
                ingress_topic_name="topic",
                ingress_subscription_name=None,
            )
        self.assertIn(
            "INGRESS_TOPIC_NAME and INGRESS_SUBSCRIPTION_NAME must both be set",
            str(context.exception),
        )

    def test_valid_queue_ingress_does_not_raise(self) -> None:
        validate_ingress_config(
            ingress_queue_name="queue",
            ingress_topic_name=None,
            ingress_subscription_name=None,
        )

    def test_valid_topic_ingress_does_not_raise(self) -> None:
        validate_ingress_config(
            ingress_queue_name=None,
            ingress_topic_name="topic",
            ingress_subscription_name="subscription",
        )

    def test_app_config_construction_does_not_validate_ingress(self) -> None:
        # AppConfig is a plain data holder - many callers (e.g. transformer test fixtures)
        # construct it with partial/placeholder ingress fields irrelevant to what they're
        # testing. Ingress validation happens at startup (run_transformer_app), not here.
        AppConfig(
            connection_string=None,
            ingress_queue_name=None,
            ingress_session_id=None,
            egress_queue_name="egress_queue",
            egress_session_id=None,
            service_bus_namespace=None,
            workflow_id="workflow_id",
            microservice_id="microservice_id",
            health_check_hostname=None,
            health_check_port=None,
        )


if __name__ == "__main__":
    unittest.main()
