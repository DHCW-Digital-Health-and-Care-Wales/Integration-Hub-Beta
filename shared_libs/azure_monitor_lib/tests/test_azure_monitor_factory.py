import os
import unittest
from unittest.mock import MagicMock, patch

from azure_monitor_lib.azure_monitor_factory import AzureMonitorFactory


class TestAzureMonitorFactory(unittest.TestCase):
    def setUp(self):
        # Reset factory state for each test
        AzureMonitorFactory._initialized = False
        AzureMonitorFactory._meter = None
        AzureMonitorFactory._is_enabled = None
        AzureMonitorFactory._connection_string = None
        AzureMonitorFactory._uami_client_id = None

    def test_is_enabled_with_valid_connection_string(self):
        """Test is_enabled returns True when APPLICATIONINSIGHTS_CONNECTION_STRING is set."""
        with patch.dict(os.environ, {"APPLICATIONINSIGHTS_CONNECTION_STRING": "test-connection-string"}):
            result = AzureMonitorFactory.is_enabled()
            self.assertTrue(result)

    def test_is_enabled_with_empty_connection_string(self):
        """Test is_enabled returns False when APPLICATIONINSIGHTS_CONNECTION_STRING is empty or missing."""
        test_cases = [
            {"APPLICATIONINSIGHTS_CONNECTION_STRING": ""},
            {"APPLICATIONINSIGHTS_CONNECTION_STRING": "   "},
            {},  # Not set at all
        ]

        for env_vars in test_cases:
            with self.subTest(env_vars=env_vars):
                # Reset cached values
                AzureMonitorFactory._is_enabled = None
                AzureMonitorFactory._connection_string = None

                with patch.dict(os.environ, env_vars, clear=True):
                    result = AzureMonitorFactory.is_enabled()
                    self.assertFalse(result)

    @patch("azure_monitor_lib.azure_monitor_factory.configure_azure_monitor")
    @patch("azure_monitor_lib.azure_monitor_factory.metrics.get_meter")
    @patch("azure_monitor_lib.azure_monitor_factory.AzureMonitorFactory._get_credential")
    def test_ensure_initialized_success(self, mock_get_credential, mock_get_meter, mock_configure):
        """Test successful initialization of Azure Monitor."""
        with patch.dict(os.environ, {"APPLICATIONINSIGHTS_CONNECTION_STRING": "test-connection"}):
            mock_credential = MagicMock()
            mock_meter = MagicMock()
            mock_get_credential.return_value = mock_credential
            mock_get_meter.return_value = mock_meter

            result = AzureMonitorFactory.ensure_initialized()

            self.assertTrue(result)
            self.assertTrue(AzureMonitorFactory._initialized)
            self.assertEqual(AzureMonitorFactory._meter, mock_meter)

    def test_ensure_initialized_disabled(self):
        """Test that ensure_initialized returns False when Azure Monitor is disabled."""
        with patch.dict(os.environ, {}, clear=True):  # No connection string
            with patch("azure_monitor_lib.azure_monitor_factory.logger") as mock_logger:
                result = AzureMonitorFactory.ensure_initialized()

                self.assertFalse(result)
                self.assertFalse(AzureMonitorFactory._initialized)
                mock_logger.info.assert_called_once()

    @patch("azure_monitor_lib.azure_monitor_factory.ManagedIdentityCredential")
    @patch("azure_monitor_lib.azure_monitor_factory.DefaultAzureCredential")
    def test_get_credential_with_uami_client_id(self, mock_default_cred, mock_managed_cred):
        """Test _get_credential returns ManagedIdentityCredential when UAMI client ID is set."""
        with patch.dict(os.environ, {"INSIGHTS_UAMI_CLIENT_ID": "test-client-id"}):
            mock_credential = MagicMock()
            mock_managed_cred.return_value = mock_credential

            result = AzureMonitorFactory._get_credential()

            self.assertEqual(result, mock_credential)
            mock_managed_cred.assert_called_once_with(client_id="test-client-id")
            mock_default_cred.assert_not_called()


if __name__ == "__main__":
    unittest.main()