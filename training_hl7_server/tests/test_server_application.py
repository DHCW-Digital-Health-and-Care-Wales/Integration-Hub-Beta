"""Unit tests for server_application module."""

import os
import unittest
from typing import Dict
from unittest.mock import MagicMock, patch

from training_hl7_server.server_application import TrainingHl7ServerApplication

ENV_VARS_NO_SERVICE_BUS: Dict[str, str] = {
    "HOST": "127.0.0.1",
    "PORT": "2575",
    "HL7_VERSION": "2.3.1",
    "ALLOWED_SENDERS": "169,245",
}

ENV_VARS_WITH_SERVICE_BUS: Dict[str, str] = {
    "HOST": "127.0.0.1",
    "PORT": "2575",
    "HL7_VERSION": "2.3.1",
    "ALLOWED_SENDERS": "169,245",
    "SERVICE_BUS_CONNECTION_STRING": "Endpoint=sb://localhost",
    "EGRESS_QUEUE_NAME": "training_queue",
    "EGRESS_SESSION_ID": "session_123",
}


class TestTrainingHl7ServerApplication(unittest.TestCase):
    """Test cases for TrainingHl7ServerApplication class."""

    @patch.dict(os.environ, ENV_VARS_NO_SERVICE_BUS, clear=True)
    def test_init_loads_config(self) -> None:
        """Test that __init__ loads configuration from environment variables."""
        app = TrainingHl7ServerApplication()

        # Verify config is loaded
        self.assertIsNotNone(app.config)
        self.assertEqual(app.config.host, "127.0.0.1")
        self.assertEqual(app.config.port, 2575)
        self.assertEqual(app.config.hl7_version, "2.3.1")
        self.assertEqual(app.config.allowed_senders, "169,245")

    @patch.dict(os.environ, ENV_VARS_NO_SERVICE_BUS, clear=True)
    def test_init_sets_server_to_none(self) -> None:
        """Test that __init__ initializes server-related attributes to None."""
        app = TrainingHl7ServerApplication()

        # Verify server attributes are None before start_server is called
        self.assertIsNone(app.server)
        self.assertIsNone(app.server_thread)
        self.assertIsNone(app.sender_client)

    @patch.dict(os.environ, ENV_VARS_WITH_SERVICE_BUS, clear=True)
    def test_config_with_service_bus_settings(self) -> None:
        """Test that Service Bus configuration is loaded from environment."""
        app = TrainingHl7ServerApplication()

        # Verify Service Bus config is loaded
        self.assertEqual(app.config.connection_string, "Endpoint=sb://localhost")
        self.assertEqual(app.config.egress_queue_name, "training_queue")
        self.assertEqual(app.config.egress_session_id, "session_123")

    @patch.dict(os.environ, ENV_VARS_NO_SERVICE_BUS, clear=True)
    def test_start_server_without_service_bus(self) -> None:
        """Test that app initializes without Service Bus when not configured."""
        app = TrainingHl7ServerApplication()

        # Verify sender_client is None when Service Bus is not configured
        self.assertIsNone(app.sender_client)

        # Verify config does not have Service Bus settings
        self.assertIsNone(app.config.connection_string)
        self.assertIsNone(app.config.egress_queue_name)

    @patch.dict(os.environ, ENV_VARS_NO_SERVICE_BUS, clear=True)
    def test_signal_handler_registered(self) -> None:
        """Test that signal handlers are registered."""
        import signal

        # Store original handlers
        original_sigint = signal.getsignal(signal.SIGINT)
        original_sigterm = signal.getsignal(signal.SIGTERM)

        TrainingHl7ServerApplication()

        # Verify signal handlers were modified
        new_sigint = signal.getsignal(signal.SIGINT)
        new_sigterm = signal.getsignal(signal.SIGTERM)

        # Handlers should be set to the app's _signal_handler method
        self.assertIsNotNone(new_sigint)
        self.assertIsNotNone(new_sigterm)
        self.assertNotEqual(new_sigint, original_sigint)
        self.assertNotEqual(new_sigterm, original_sigterm)

    @patch.dict(os.environ, ENV_VARS_NO_SERVICE_BUS, clear=True)
    @patch("training_hl7_server.server_application.MLLPServer")
    def test_stop_server_closes_resources(self, mock_mllp_server: MagicMock) -> None:
        """Test that stop_server properly closes server and Service Bus client."""
        app = TrainingHl7ServerApplication()

        # Set up mock server
        mock_server = MagicMock()
        app.server = mock_server

        # Set up mock sender client
        mock_sender_client = MagicMock()
        app.sender_client = mock_sender_client

        # Call stop_server
        app.stop_server()

        # Verify server shutdown was called
        mock_server.shutdown.assert_called_once()

        # Verify sender client close was called
        mock_sender_client.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
