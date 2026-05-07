import unittest
from typing import Dict, Optional
from unittest.mock import Mock, patch

from adt_receiver.app_config import DEFAULT_MAX_MESSAGE_SIZE_BYTES, AppConfig


class TestAppConfig(unittest.TestCase):

    @patch("adt_receiver.app_config.os.getenv")
    def test_read_env_config_returns_config_with_defaults(self, mock_getenv: Mock) -> None:
        def getenv_side_effect(name: str) -> Optional[str]:
            values: Dict[str, str] = {
                "SERVICE_BUS_CONNECTION_STRING": "conn_str",
                "EGRESS_QUEUE_NAME": "egress_queue",
                "SERVICE_BUS_NAMESPACE": "namespace",
                "AUDIT_QUEUE_NAME": "audit-queue",
                "WORKFLOW_ID": "test-workflow",
                "MICROSERVICE_ID": "test-microservice",
                "HEALTH_BOARD": "test-health-board",
                "PEER_SERVICE": "test-service",
                "HL7_VERSION": "2.5",
                "SENDING_APP": "test_app",
                "HEALTH_CHECK_HOST": "localhost",
                "HEALTH_CHECK_PORT": "8080",
            }
            return values.get(name)

        mock_getenv.side_effect = getenv_side_effect

        config = AppConfig.read_env_config()

        self.assertEqual(config.connection_string, "conn_str")
        self.assertEqual(config.egress_queue_name, "egress_queue")
        self.assertEqual(config.audit_queue_name, "audit-queue")
        self.assertEqual(config.workflow_id, "test-workflow")
        self.assertEqual(config.microservice_id, "test-microservice")
        self.assertEqual(config.hl7_version, "2.5")
        self.assertEqual(config.sending_app, "test_app")
        self.assertEqual(config.health_check_hostname, "localhost")
        self.assertEqual(config.health_check_port, 8080)
        self.assertEqual(config.max_message_size_bytes, DEFAULT_MAX_MESSAGE_SIZE_BYTES)

    @patch("adt_receiver.app_config.os.getenv")
    def test_read_env_config_requires_queue_or_topic(self, mock_getenv: Mock) -> None:
        def getenv_side_effect(name: str) -> Optional[str]:
            values: Dict[str, str] = {
                "AUDIT_QUEUE_NAME": "audit-queue",
                "WORKFLOW_ID": "test-workflow",
                "MICROSERVICE_ID": "test-microservice",
                "HEALTH_BOARD": "test-health-board",
                "PEER_SERVICE": "test-service",
            }
            return values.get(name)

        mock_getenv.side_effect = getenv_side_effect

        with self.assertRaises(RuntimeError) as context:
            AppConfig.read_env_config()

        self.assertIn("EGRESS_QUEUE_NAME", str(context.exception))

    @patch("adt_receiver.app_config.os.getenv")
    def test_read_env_config_rejects_both_queue_and_topic(self, mock_getenv: Mock) -> None:
        def getenv_side_effect(name: str) -> Optional[str]:
            values: Dict[str, str] = {
                "EGRESS_QUEUE_NAME": "a-queue",
                "EGRESS_TOPIC_NAME": "a-topic",
                "AUDIT_QUEUE_NAME": "audit-queue",
                "WORKFLOW_ID": "test-workflow",
                "MICROSERVICE_ID": "test-microservice",
                "HEALTH_BOARD": "test-health-board",
                "PEER_SERVICE": "test-service",
            }
            return values.get(name)

        mock_getenv.side_effect = getenv_side_effect

        with self.assertRaises(RuntimeError) as context:
            AppConfig.read_env_config()

        self.assertIn("Cannot specify both", str(context.exception))

    @patch("adt_receiver.app_config.os.getenv")
    def test_read_env_config_missing_required_field_raises_error(self, mock_getenv: Mock) -> None:
        def getenv_side_effect(name: str) -> Optional[str]:
            values: Dict[str, str] = {
                "EGRESS_QUEUE_NAME": "egress_queue",
                "WORKFLOW_ID": "test-workflow",
                "MICROSERVICE_ID": "test-microservice",
                "HEALTH_BOARD": "test-health-board",
                "PEER_SERVICE": "test-service",
                # AUDIT_QUEUE_NAME intentionally omitted
            }
            return values.get(name)

        mock_getenv.side_effect = getenv_side_effect

        with self.assertRaises(RuntimeError) as context:
            AppConfig.read_env_config()

        self.assertIn("Missing required configuration", str(context.exception))

    @patch("adt_receiver.app_config.os.getenv")
    def test_read_env_config_handles_none_optional_fields(self, mock_getenv: Mock) -> None:
        def getenv_side_effect(name: str) -> Optional[str]:
            values: Dict[str, str] = {
                "EGRESS_QUEUE_NAME": "egress_queue",
                "AUDIT_QUEUE_NAME": "audit-queue",
                "WORKFLOW_ID": "test-workflow",
                "MICROSERVICE_ID": "test-microservice",
                "HEALTH_BOARD": "test-health-board",
                "PEER_SERVICE": "test-service",
            }
            return values.get(name)

        mock_getenv.side_effect = getenv_side_effect

        config = AppConfig.read_env_config()

        self.assertIsNone(config.connection_string)
        self.assertIsNone(config.service_bus_namespace)
        self.assertIsNone(config.hl7_version)
        self.assertIsNone(config.sending_app)
        self.assertIsNone(config.health_check_hostname)
        self.assertIsNone(config.health_check_port)
        self.assertEqual(config.max_message_size_bytes, DEFAULT_MAX_MESSAGE_SIZE_BYTES)

    @patch("adt_receiver.app_config.os.getenv")
    def test_read_env_config_service_bus_limit_exceeded_raises_error(self, mock_getenv: Mock) -> None:
        def getenv_side_effect(name: str) -> Optional[str]:
            values: Dict[str, str] = {
                "EGRESS_QUEUE_NAME": "egress_queue",
                "AUDIT_QUEUE_NAME": "audit-queue",
                "WORKFLOW_ID": "test-workflow",
                "MICROSERVICE_ID": "test-microservice",
                "HEALTH_BOARD": "test-health-board",
                "PEER_SERVICE": "test-service",
                "MAX_MESSAGE_SIZE_BYTES": "104857601",
            }
            return values.get(name)

        mock_getenv.side_effect = getenv_side_effect

        with self.assertRaises(ValueError) as context:
            AppConfig.read_env_config()

        self.assertIn("exceeds Azure Service Bus Premium tier limit", str(context.exception))


if __name__ == "__main__":
    unittest.main()
