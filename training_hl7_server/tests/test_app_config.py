"""Unit tests for app_config module."""

import unittest
from typing import Dict, Optional
from unittest.mock import Mock, patch

from training_hl7_server.app_config import AppConfig


class TestAppConfig(unittest.TestCase):
    """Test cases for AppConfig class."""

    @patch("training_hl7_server.app_config.os.getenv")
    def test_read_env_config_returns_config_with_defaults(self, mock_getenv: Mock) -> None:
        """Test that read_env_config applies default values when environment variables are not set."""

        def getenv_side_effect(name: str) -> Optional[str]:
            values: Dict[str, str] = {
                # Required environment variables
                "HOST": "127.0.0.1",
                "PORT": "2575",
                # Optional environment variables
                "HL7_VERSION": "2.3.1",
                "ALLOWED_SENDERS": "169,245",
            }
            return values.get(name)

        mock_getenv.side_effect = getenv_side_effect

        config = AppConfig.read_env_config()

        # Verify network settings
        self.assertEqual(config.host, "127.0.0.1")
        self.assertEqual(config.port, 2575)

        # Verify validation settings
        self.assertEqual(config.hl7_version, "2.3.1")
        self.assertEqual(config.allowed_senders, "169,245")

        # Verify Service Bus settings are None when not provided
        self.assertIsNone(config.connection_string)
        self.assertIsNone(config.egress_queue_name)
        self.assertIsNone(config.egress_session_id)

    @patch("training_hl7_server.app_config.os.getenv")
    def test_read_env_config_with_service_bus_settings(self, mock_getenv: Mock) -> None:
        """Test that Service Bus configuration is properly loaded."""

        def getenv_side_effect(name: str) -> Optional[str]:
            values: Dict[str, str] = {
                "HOST": "127.0.0.1",
                "PORT": "2576",
                "SERVICE_BUS_CONNECTION_STRING": "Endpoint=sb://localhost",
                "EGRESS_QUEUE_NAME": "training_queue",
                "EGRESS_SESSION_ID": "session_123",
            }
            return values.get(name)

        mock_getenv.side_effect = getenv_side_effect

        config = AppConfig.read_env_config()

        # Verify Service Bus settings
        self.assertEqual(config.connection_string, "Endpoint=sb://localhost")
        self.assertEqual(config.egress_queue_name, "training_queue")
        self.assertEqual(config.egress_session_id, "session_123")

    @patch("training_hl7_server.app_config.os.getenv")
    def test_read_env_config_applies_defaults(self, mock_getenv: Mock) -> None:
        """Test that default values are applied when optional env vars are missing."""

        def getenv_side_effect(name: str) -> Optional[str]:
            # Only provide minimal required values
            values: Dict[str, str] = {}
            return values.get(name)

        mock_getenv.side_effect = getenv_side_effect

        config = AppConfig.read_env_config()

        # Verify defaults are applied
        self.assertEqual(config.host, "127.0.0.1")
        self.assertEqual(config.port, 2575)
        self.assertIsNone(config.hl7_version)
        self.assertIsNone(config.allowed_senders)


if __name__ == "__main__":
    unittest.main()
