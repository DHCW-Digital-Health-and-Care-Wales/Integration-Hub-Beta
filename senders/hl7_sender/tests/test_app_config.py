import unittest
from typing import Optional
from unittest.mock import Mock, patch

from hl7_sender.app_config import AppConfig, validate_ingress_config


class TestAppConfig(unittest.TestCase):
    @patch("hl7_sender.app_config.os.getenv")
    def test_read_env_config_returns_config(self, mock_getenv: Mock) -> None:
        def getenv_side_effect(name: str) -> Optional[str]:
            values = {
                "SERVICE_BUS_CONNECTION_STRING": "conn_str",
                "INGRESS_QUEUE_NAME": "ingress_queue",
                "INGRESS_SESSION_ID": "ingress_session",
                "SERVICE_BUS_NAMESPACE": "namespace",
                "RECEIVER_MLLP_HOST": "localhost",
                "RECEIVER_MLLP_PORT": "1234",
                "MESSAGE_STORE_QUEUE_NAME": "messagestore-queue",
                "WORKFLOW_ID": "test-workflow",
                "MICROSERVICE_ID": "test-microservice",
                "HEALTH_BOARD": "test health board",
                "PEER_SERVICE": "test-service",
                "ACK_TIMEOUT_SECONDS": "30",
            }
            return values.get(name)

        mock_getenv.side_effect = getenv_side_effect

        config = AppConfig.read_env_config()
        self.assertEqual(config.connection_string, "conn_str")
        self.assertEqual(config.ingress_queue_name, "ingress_queue")
        self.assertEqual(config.service_bus_namespace, "namespace")
        self.assertEqual(config.receiver_mllp_hostname, "localhost")
        self.assertEqual(config.receiver_mllp_port, 1234)
        self.assertEqual(config.message_store_queue_name, "messagestore-queue")
        self.assertEqual(config.workflow_id, "test-workflow")
        self.assertEqual(config.microservice_id, "test-microservice")
        self.assertEqual(config.health_board, "test health board")
        self.assertEqual(config.peer_service, "test-service")

    @patch("hl7_sender.app_config.os.getenv")
    def test_read_env_config_message_store_queue_name_optional_when_unset(self, mock_getenv: Mock) -> None:
        def getenv_side_effect(name: str) -> Optional[str]:
            values = {
                "INGRESS_QUEUE_NAME": "ingress_queue",
                "INGRESS_SESSION_ID": "ingress_session",
                "RECEIVER_MLLP_HOST": "localhost",
                "RECEIVER_MLLP_PORT": "1234",
                # MESSAGE_STORE_QUEUE_NAME omitted — should be optional regardless of MESSAGE_STORE_ENABLED
                "WORKFLOW_ID": "test-workflow",
                "MICROSERVICE_ID": "test-microservice",
                "HEALTH_BOARD": "test health board",
                "PEER_SERVICE": "test-service",
            }
            return values.get(name)

        mock_getenv.side_effect = getenv_side_effect

        config = AppConfig.read_env_config()

        self.assertIsNone(config.message_store_queue_name)
        self.assertEqual(config.ack_timeout_seconds, 30)

    @patch("hl7_sender.app_config.os.getenv")
    def test_read_env_config_supports_topic_subscription_ingress(self, mock_getenv: Mock) -> None:
        def getenv_side_effect(name: str) -> Optional[str]:
            values = {
                "SERVICE_BUS_CONNECTION_STRING": "conn_str",
                "INGRESS_TOPIC_NAME": "ingress-topic",
                "INGRESS_SUBSCRIPTION_NAME": "ingress-subscription",
                "INGRESS_SESSION_ID": "ingress_session",
                "SERVICE_BUS_NAMESPACE": "namespace",
                "RECEIVER_MLLP_HOST": "localhost",
                "RECEIVER_MLLP_PORT": "1234",
                "WORKFLOW_ID": "test-workflow",
                "MICROSERVICE_ID": "test-microservice",
                "HEALTH_BOARD": "test health board",
                "PEER_SERVICE": "test-service",
                "ACK_TIMEOUT_SECONDS": "30",
            }
            return values.get(name)

        mock_getenv.side_effect = getenv_side_effect

        config = AppConfig.read_env_config()

        self.assertIsNone(config.ingress_queue_name)
        self.assertEqual(config.ingress_topic_name, "ingress-topic")
        self.assertEqual(config.ingress_subscription_name, "ingress-subscription")

    @patch("hl7_sender.app_config.os.getenv")
    def test_read_env_config_missing_required_env_var_raises_error(self, mock_getenv: Mock) -> None:
        mock_getenv.return_value = None
        with self.assertRaises(RuntimeError) as context:
            AppConfig.read_env_config()
        self.assertIn("Missing required configuration", str(context.exception))

    def test_validate_ingress_config_rejects_combined_queue_and_topic(self) -> None:
        with self.assertRaises(RuntimeError):
            validate_ingress_config("queue-a", "topic-a", "sub-a")


if __name__ == "__main__":
    unittest.main()
