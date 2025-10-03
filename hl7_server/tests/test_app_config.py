import unittest
from typing import Dict, Optional
from unittest.mock import Mock, patch

from hl7_server.app_config import DEFAULT_MAX_MESSAGE_SIZE_BYTES, AppConfig


class TestAppConfig(unittest.TestCase):

    @patch("hl7_server.app_config.os.getenv")
    def test_read_env_config_returns_config_with_defaults(self, mock_getenv: Mock) -> None:
        def getenv_side_effect(name: str) -> Optional[str]:
            values: Dict[str, str] = {
                "SERVICE_BUS_CONNECTION_STRING": "conn_str",
                "EGRESS_QUEUE_NAME": "egress_queue",
                "SERVICE_BUS_NAMESPACE": "namespace",
                "AUDIT_QUEUE_NAME": "audit-queue",
                "WORKFLOW_ID": "test-workflow",
                "MICROSERVICE_ID": "test-microservice",
                "HL7_VERSION": "2.5.1",
                "SENDING_APP": "test_app",
                "HEALTH_CHECK_HOST": "localhost",
                "HEALTH_CHECK_PORT": "8080",
                "HL7_VALIDATION_FLOW": "test_flow"
                # MAX_MESSAGE_SIZE_BYTES intentionally omitted to test default
            }
            return values.get(name)

        mock_getenv.side_effect = getenv_side_effect

        config = AppConfig.read_env_config()

        self.assertEqual(config.connection_string, "conn_str")
        self.assertEqual(config.egress_queue_name, "egress_queue")
        self.assertEqual(config.service_bus_namespace, "namespace")
        self.assertEqual(config.audit_queue_name, "audit-queue")
        self.assertEqual(config.workflow_id, "test-workflow")
        self.assertEqual(config.microservice_id, "test-microservice")
        self.assertEqual(config.hl7_version, "2.5.1")
        self.assertEqual(config.sending_app, "test_app")
        self.assertEqual(config.health_check_hostname, "localhost")
        self.assertEqual(config.health_check_port, 8080)
        self.assertEqual(config.hl7_validation_flow, "test_flow")

        # Verify default message size is applied when not configured
        self.assertEqual(config.max_message_size_bytes, DEFAULT_MAX_MESSAGE_SIZE_BYTES)

    @patch("hl7_server.app_config.os.getenv")
    def test_read_env_config_with_custom_message_size(self, mock_getenv: Mock) -> None:
        def getenv_side_effect(name: str) -> Optional[str]:
            values: Dict[str, str] = {
                "EGRESS_QUEUE_NAME": "egress_queue",
                "AUDIT_QUEUE_NAME": "audit-queue",
                "WORKFLOW_ID": "test-workflow",
                "MICROSERVICE_ID": "test-microservice",
                "MAX_MESSAGE_SIZE_BYTES": "2097152"  # 2MB custom size
            }
            return values.get(name)

        mock_getenv.side_effect = getenv_side_effect

        config = AppConfig.read_env_config()
        self.assertEqual(config.max_message_size_bytes, 2097152)

    @patch("hl7_server.app_config.os.getenv")
    def test_read_env_config_service_bus_limit_exceeded_raises_error(self, mock_getenv: Mock) -> None:
        def getenv_side_effect(name: str) -> Optional[str]:
            values: Dict[str, str] = {
                "EGRESS_QUEUE_NAME": "egress_queue",
                "AUDIT_QUEUE_NAME": "audit-queue",
                "WORKFLOW_ID": "test-workflow",
                "MICROSERVICE_ID": "test-microservice",
                "MAX_MESSAGE_SIZE_BYTES": "104857601"  # 1 byte over 100MB limit
            }
            return values.get(name)

        mock_getenv.side_effect = getenv_side_effect

        with self.assertRaises(ValueError) as context:
            AppConfig.read_env_config()

        error_message = str(context.exception)
        self.assertIn("exceeds Azure Service Bus Premium tier limit", error_message)
        self.assertIn("104857600 bytes", error_message)
        self.assertIn("100.0MB", error_message)

    @patch("hl7_server.app_config.os.getenv")
    def test_read_env_config_exactly_at_service_bus_limit(self, mock_getenv: Mock) -> None:
        def getenv_side_effect(name: str) -> Optional[str]:
            values: Dict[str, str] = {
                "EGRESS_QUEUE_NAME": "egress_queue",
                "AUDIT_QUEUE_NAME": "audit-queue",
                "WORKFLOW_ID": "test-workflow",
                "MICROSERVICE_ID": "test-microservice",
                "MAX_MESSAGE_SIZE_BYTES": "104857600"  # Exactly 100MB
            }
            return values.get(name)

        mock_getenv.side_effect = getenv_side_effect

        config = AppConfig.read_env_config()
        self.assertEqual(config.max_message_size_bytes, 104857600)

    @patch("hl7_server.app_config.os.getenv")
    def test_read_env_config_missing_required_field_raises_error(self, mock_getenv: Mock) -> None:
        mock_getenv.return_value = None

        with self.assertRaises(RuntimeError) as context:
            AppConfig.read_env_config()

        self.assertIn("Missing required configuration", str(context.exception))

    @patch("hl7_server.app_config.os.getenv")
    def test_read_env_config_handles_none_optional_fields(self, mock_getenv: Mock) -> None:
        def getenv_side_effect(name: str) -> Optional[str]:
            required_values: Dict[str, str] = {
                "EGRESS_QUEUE_NAME": "egress_queue",
                "AUDIT_QUEUE_NAME": "audit-queue",
                "WORKFLOW_ID": "test-workflow",
                "MICROSERVICE_ID": "test-microservice"
            }
            return required_values.get(name)  # Returns None for optional fields

        mock_getenv.side_effect = getenv_side_effect

        config = AppConfig.read_env_config()

        # Verify required fields are loaded
        self.assertEqual(config.egress_queue_name, "egress_queue")
        self.assertEqual(config.audit_queue_name, "audit-queue")
        self.assertEqual(config.workflow_id, "test-workflow")
        self.assertEqual(config.microservice_id, "test-microservice")

        # Verify optional fields default to None
        self.assertIsNone(config.connection_string)
        self.assertIsNone(config.service_bus_namespace)
        self.assertIsNone(config.hl7_version)
        self.assertIsNone(config.sending_app)
        self.assertIsNone(config.health_check_hostname)
        self.assertIsNone(config.health_check_port)
        self.assertIsNone(config.hl7_validation_flow)

        # Verify message size uses default when not configured
        self.assertEqual(config.max_message_size_bytes, DEFAULT_MAX_MESSAGE_SIZE_BYTES)


if __name__ == "__main__":
    unittest.main()
