import unittest
from unittest.mock import patch

from monitoring_service.app_config import MonitoringAppConfig


class TestMonitoringAppConfig(unittest.TestCase):
    
    @patch("monitoring_service.app_config.os.getenv")
    def test_read_env_config_returns_config_with_all_values(self, mock_getenv):
        """Test that read_env_config returns a properly configured AppConfig when all environment variables are set."""
        def getenv_side_effect(name):
            values = {
                "SERVICE_BUS_CONNECTION_STRING": "Endpoint=sb://test.servicebus.windows.net/;SharedAccessKeyName=test;SharedAccessKey=testkey",
                "SERVICE_BUS_NAMESPACE": "test-namespace",
                "AUDIT_QUEUE_NAME": "audit-queue",
                "DATABASE_CONNECTION_STRING": "DRIVER=test;SERVER=test;DATABASE=test;UID=test;PWD=test",
                "HEALTH_CHECK_HOST": "localhost",
                "HEALTH_CHECK_PORT": "8080",
            }
            return values.get(name)

        mock_getenv.side_effect = getenv_side_effect

        config = MonitoringAppConfig.read_env_config()
        
        self.assertEqual(config.connection_string, "Endpoint=sb://test.servicebus.windows.net/;SharedAccessKeyName=test;SharedAccessKey=testkey")
        self.assertEqual(config.service_bus_namespace, "test-namespace")
        self.assertEqual(config.audit_queue_name, "audit-queue")
        self.assertEqual(config.database_connection_string, "DRIVER=test;SERVER=test;DATABASE=test;UID=test;PWD=test")
        self.assertEqual(config.health_check_hostname, "localhost")
        self.assertEqual(config.health_check_port, 8080)

    @patch("monitoring_service.app_config.os.getenv")
    def test_read_env_config_returns_config_with_optional_values_none(self, mock_getenv):
        """Test that read_env_config returns config with None values for optional fields when not set."""
        def getenv_side_effect(name):
            values = {
                "AUDIT_QUEUE_NAME": "audit-queue",
                "DATABASE_CONNECTION_STRING": "DRIVER=test;SERVER=test;DATABASE=test;UID=test;PWD=test",
            }
            return values.get(name)

        mock_getenv.side_effect = getenv_side_effect

        config = MonitoringAppConfig.read_env_config()
        
        self.assertIsNone(config.connection_string)
        self.assertIsNone(config.service_bus_namespace)
        self.assertEqual(config.audit_queue_name, "audit-queue")
        self.assertEqual(config.database_connection_string, "DRIVER=test;SERVER=test;DATABASE=test;UID=test;PWD=test")
        self.assertIsNone(config.health_check_hostname)
        self.assertIsNone(config.health_check_port)

    @patch("monitoring_service.app_config.os.getenv")
    def test_read_env_config_missing_audit_queue_name_raises_error(self, mock_getenv):
        """Test that missing required AUDIT_QUEUE_NAME raises RuntimeError."""
        def getenv_side_effect(name):
            values = {
                "DATABASE_CONNECTION_STRING": "DRIVER=test;SERVER=test;DATABASE=test;UID=test;PWD=test",
            }
            return values.get(name)

        mock_getenv.side_effect = getenv_side_effect

        with self.assertRaises(RuntimeError) as context:
            MonitoringAppConfig.read_env_config()
        self.assertIn("Missing required configuration: AUDIT_QUEUE_NAME", str(context.exception))

    @patch("monitoring_service.app_config.os.getenv")
    def test_read_env_config_missing_database_connection_string_raises_error(self, mock_getenv):
        """Test that missing required DATABASE_CONNECTION_STRING raises RuntimeError."""
        def getenv_side_effect(name):
            values = {
                "AUDIT_QUEUE_NAME": "audit-queue",
            }
            return values.get(name)

        mock_getenv.side_effect = getenv_side_effect

        with self.assertRaises(RuntimeError) as context:
            MonitoringAppConfig.read_env_config()
        self.assertIn("Missing required configuration: DATABASE_CONNECTION_STRING", str(context.exception))

    @patch("monitoring_service.app_config.os.getenv")
    def test_read_env_config_empty_string_required_field_raises_error(self, mock_getenv):
        """Test that empty string for required field raises RuntimeError."""
        def getenv_side_effect(name):
            values = {
                "AUDIT_QUEUE_NAME": "   ",
                "DATABASE_CONNECTION_STRING": "DRIVER=test;SERVER=test;DATABASE=test;UID=test;PWD=test",
            }
            return values.get(name)

        mock_getenv.side_effect = getenv_side_effect

        with self.assertRaises(RuntimeError) as context:
            MonitoringAppConfig.read_env_config()
        self.assertIn("Missing required configuration: AUDIT_QUEUE_NAME", str(context.exception))

    @patch("monitoring_service.app_config.os.getenv")
    def test_read_env_config_invalid_health_check_port_raises_error(self, mock_getenv):
        """Test that invalid integer value for HEALTH_CHECK_PORT raises RuntimeError."""
        def getenv_side_effect(name):
            values = {
                "AUDIT_QUEUE_NAME": "audit-queue",
                "DATABASE_CONNECTION_STRING": "DRIVER=test;SERVER=test;DATABASE=test;UID=test;PWD=test",
                "HEALTH_CHECK_PORT": "not_a_number",
            }
            return values.get(name)

        mock_getenv.side_effect = getenv_side_effect

        with self.assertRaises(RuntimeError) as context:
            MonitoringAppConfig.read_env_config()
        self.assertIn("Invalid integer value for HEALTH_CHECK_PORT: not_a_number", str(context.exception))

    @patch("monitoring_service.app_config.os.getenv")
    def test_read_env_config_valid_health_check_port_converts_to_int(self, mock_getenv):
        """Test that valid string port number is converted to integer."""
        def getenv_side_effect(name):
            values = {
                "AUDIT_QUEUE_NAME": "audit-queue",
                "DATABASE_CONNECTION_STRING": "DRIVER=test;SERVER=test;DATABASE=test;UID=test;PWD=test",
                "HEALTH_CHECK_PORT": "9090",
            }
            return values.get(name)

        mock_getenv.side_effect = getenv_side_effect

        config = MonitoringAppConfig.read_env_config()
        
        self.assertEqual(config.health_check_port, 9090)
        self.assertIsInstance(config.health_check_port, int)


if __name__ == "__main__":
    unittest.main()