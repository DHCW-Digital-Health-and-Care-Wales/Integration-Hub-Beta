import os
import unittest
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import MagicMock, patch

from event_logger_lib.event_logger import EventLogger
from event_logger_lib.log_event import EventType


class TestEventLogger(unittest.TestCase):
    def setUp(self):
        self.workflow_id = "test-workflow"
        self.microservice_id = "test-service"

        with patch.dict(
            os.environ,
            {
                "APPLICATIONINSIGHTS_CONNECTION_STRING": "InstrumentationKey=test-key;IngestionEndpoint=test-endpoint",
            },
        ):
            with patch("azure_monitor_lib.AzureMonitorFactory.ensure_initialized", return_value=True):
                with patch("azure_monitor_lib.AzureMonitorFactory.is_enabled", return_value=True):
                    from azure_monitor_lib import AzureMonitorFactory
                    self.event_logger = EventLogger(
                        self.workflow_id, self.microservice_id, AzureMonitorFactory
                    )

    def tearDown(self):
        from azure_monitor_lib import AzureMonitorFactory
        AzureMonitorFactory._initialized = False
        AzureMonitorFactory._meter = None
        AzureMonitorFactory._is_enabled = None
        AzureMonitorFactory._connection_string = None
        AzureMonitorFactory._uami_client_id = None

    def _assert_log_event(
        self,
        mock_logger: MagicMock,
        event_type: str,
        message_content: str,
        timestamp: str,
        validation_result: Optional[str] = None,
        error_details: Optional[str] = None,
    ) -> None:
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        self.assertEqual(call_args[0][0], "Integration Hub Event")

        extra = call_args[1]["extra"]
        self.assertEqual(extra["workflow_id"], self.workflow_id)
        self.assertEqual(extra["microservice_id"], self.microservice_id)
        self.assertEqual(extra["event_type"], event_type)
        self.assertEqual(extra["message_content"], message_content)
        self.assertEqual(extra["timestamp"], timestamp)

        if validation_result is not None:
            self.assertEqual(extra["validation_result"], validation_result)
        else:
            self.assertIsNone(extra.get("validation_result"))

        if error_details is not None:
            self.assertEqual(extra["error_details"], error_details)
        else:
            self.assertIsNone(extra.get("error_details"))

    def test_initialization_with_logging_disabled(self):
        with patch.dict(
            os.environ, {"APPLICATIONINSIGHTS_CONNECTION_STRING": ""}, clear=True
        ):
            from azure_monitor_lib import AzureMonitorFactory
            logger = EventLogger("test-workflow", "test-service", AzureMonitorFactory)
            self.assertFalse(logger.azure_monitor_enabled)

    def test_initialization_with_logging_disabled_no_env_var(self):
        with patch.dict(os.environ, {}, clear=True):
            from azure_monitor_lib import AzureMonitorFactory
            logger = EventLogger("test-workflow", "test-service", AzureMonitorFactory)
            self.assertFalse(logger.azure_monitor_enabled)

    def test_initialization_with_logging_disabled_whitespace_only(self):
        with patch.dict(
            os.environ, {"APPLICATIONINSIGHTS_CONNECTION_STRING": "   "}, clear=True
        ):
            from azure_monitor_lib import AzureMonitorFactory
            logger = EventLogger("test-workflow", "test-service", AzureMonitorFactory)
            self.assertFalse(logger.azure_monitor_enabled)

    def test_initialization_with_logging_enabled(self):
        with patch.dict(
            os.environ,
            {
                "APPLICATIONINSIGHTS_CONNECTION_STRING": "InstrumentationKey=test-key;IngestionEndpoint=test-endpoint",
            },
        ):
            with patch(
                "azure_monitor_lib.AzureMonitorFactory.ensure_initialized"
            ) as mock_ensure:
                with patch(
                    "azure_monitor_lib.AzureMonitorFactory.is_enabled", return_value=True
                ) as mock_is_enabled:
                    from azure_monitor_lib import AzureMonitorFactory
                    logger = EventLogger("test-workflow", "test-service", AzureMonitorFactory)
                    self.assertTrue(logger.azure_monitor_enabled)
                    mock_ensure.assert_called_once()
                    mock_is_enabled.assert_called_once()

    def test_initialization_with_azure_monitor_failure(self):
        with patch.dict(
            os.environ,
            {
                "APPLICATIONINSIGHTS_CONNECTION_STRING": "InstrumentationKey=test-key;IngestionEndpoint=test-endpoint",
            },
        ):
            with patch(
                "azure_monitor_lib.AzureMonitorFactory.ensure_initialized",
                side_effect=Exception("Connection failed"),
            ):
                with patch("azure_monitor_lib.AzureMonitorFactory.is_enabled", return_value=True):
                    from azure_monitor_lib import AzureMonitorFactory
                    with self.assertRaises(Exception):
                        EventLogger("test-workflow", "test-service", AzureMonitorFactory)

    @patch("event_logger_lib.event_logger.datetime")
    @patch("event_logger_lib.event_logger.logger")
    def test_log_message_received_with_azure_monitor_enabled(
        self, mock_logger: MagicMock, mock_datetime: MagicMock
    ) -> None:
        # Arrange
        event_logger = self.event_logger
        mock_datetime.now.return_value = datetime(
            2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc
        )
        message_content = "Test HL7 Message"
        validation_result = "Valid"

        # Act
        event_logger.log_message_received(message_content, validation_result)

        # Assert
        self.assertTrue(event_logger.azure_monitor_enabled)
        self._assert_log_event(
            mock_logger,
            event_type=EventType.MESSAGE_RECEIVED.value,
            message_content=message_content,
            timestamp="2023-01-01T12:00:00+00:00",
            validation_result=validation_result,
        )

    @patch("event_logger_lib.event_logger.datetime")
    @patch("event_logger_lib.event_logger.logger")
    def test_log_message_received_with_azure_monitor_disabled(
        self, mock_logger: MagicMock, mock_datetime: MagicMock
    ) -> None:
        # Arrange
        with patch.dict(
            os.environ, {"APPLICATIONINSIGHTS_CONNECTION_STRING": ""}, clear=True
        ):
            from azure_monitor_lib import AzureMonitorFactory
            event_logger = EventLogger(self.workflow_id, self.microservice_id, AzureMonitorFactory)
        mock_logger.info.reset_mock()
        mock_datetime.now.return_value = datetime(
            2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc
        )
        message_content = "Test HL7 Message"
        validation_result = "Valid"

        # Act
        event_logger.log_message_received(message_content, validation_result)

        # Assert
        self.assertFalse(event_logger.azure_monitor_enabled)
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        logged_message = call_args[0][0]
        self.assertIn("Integration Hub Event:", logged_message)
        self.assertIn("'workflow_id': 'test-workflow'", logged_message)
        self.assertIn("'microservice_id': 'test-service'", logged_message)
        self.assertIn("'event_type': 'MESSAGE_RECEIVED'", logged_message)
        self.assertIn("'message_content': 'Test HL7 Message'", logged_message)
        self.assertIn("'validation_result': 'Valid'", logged_message)
        self.assertIn("'timestamp': '2023-01-01T12:00:00+00:00'", logged_message)

    @patch("event_logger_lib.event_logger.datetime")
    @patch("event_logger_lib.event_logger.logger")
    def test_log_message_processed(self, mock_logger, mock_datetime):
        # Arrange
        event_logger = self.event_logger
        mock_datetime.now.return_value = datetime(
            2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc
        )
        message_content = "Test HL7 Message"
        validation_result = "Processed successfully"

        # Act
        event_logger.log_message_processed(message_content, validation_result)

        # Assert
        self._assert_log_event(
            mock_logger,
            "MESSAGE_PROCESSED",
            message_content,
            "2025-01-01T12:00:00+00:00",
            validation_result=validation_result,
        )
        mock_logger.debug.assert_called_once_with(
            "Event logged to Azure Monitor: MESSAGE_PROCESSED"
        )

    @patch("event_logger_lib.event_logger.datetime")
    @patch("event_logger_lib.event_logger.logger")
    def test_log_message_failed(self, mock_logger, mock_datetime):
        # Arrange
        event_logger = self.event_logger
        mock_datetime.now.return_value = datetime(
            2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc
        )
        message_content = "Test HL7 Message"
        error_details = "Processing failed due to invalid format"
        validation_result = "Invalid"

        # Act
        event_logger.log_message_failed(
            message_content, error_details, validation_result
        )

        # Assert
        self._assert_log_event(
            mock_logger,
            "MESSAGE_FAILED",
            message_content,
            "2025-01-01T12:00:00+00:00",
            validation_result=validation_result,
            error_details=error_details,
        )
        mock_logger.debug.assert_called_once_with(
            "Event logged to Azure Monitor: MESSAGE_FAILED"
        )

    @patch("event_logger_lib.event_logger.datetime")
    @patch("event_logger_lib.event_logger.logger")
    def test_log_validation_result_success(self, mock_logger, mock_datetime):
        # Arrange
        event_logger = self.event_logger
        mock_datetime.now.return_value = datetime(
            2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc
        )
        message_content = "Test HL7 Message"
        validation_result = "All fields validated successfully"

        # Act
        event_logger.log_validation_result(message_content, validation_result, True)

        # Assert
        self._assert_log_event(
            mock_logger,
            "VALIDATION_SUCCESS",
            message_content,
            "2025-01-01T12:00:00+00:00",
            validation_result=validation_result,
        )
        mock_logger.debug.assert_called_once_with(
            "Event logged to Azure Monitor: VALIDATION_SUCCESS"
        )

    @patch("event_logger_lib.event_logger.datetime")
    @patch("event_logger_lib.event_logger.logger")
    def test_log_validation_result_failure(self, mock_logger, mock_datetime):
        # Arrange
        event_logger = self.event_logger
        mock_datetime.now.return_value = datetime(
            2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc
        )
        message_content = "Test HL7 Message"
        validation_result = "Missing required field: MSH.3"

        # Act
        event_logger.log_validation_result(message_content, validation_result, False)

        # Assert
        self._assert_log_event(
            mock_logger,
            "VALIDATION_FAILED",
            message_content,
            "2025-01-01T12:00:00+00:00",
            validation_result=validation_result,
        )
        mock_logger.debug.assert_called_once_with(
            "Event logged to Azure Monitor: VALIDATION_FAILED"
        )

    @patch("event_logger_lib.event_logger.logger")
    def test_send_log_event_exception_handling(self, mock_logger):
        # Arrange
        event_logger = self.event_logger
        mock_logger.info.side_effect = Exception("Something went wrong")

        # Act & Assert
        with self.assertRaises(Exception):
            event_logger.log_message_received("Test message")

        mock_logger.error.assert_called_with(
            "Failed to log event: Something went wrong"
        )

    def test_create_log_event(self):
        # Arrange
        event_logger = self.event_logger
        message_content = "Test message"
        validation_result = "Valid"
        error_details = "No errors"

        # Act
        with patch("event_logger_lib.event_logger.datetime") as mock_datetime:
            mock_datetime.now.return_value = datetime(
                2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc
            )
            event = event_logger._create_log_event(
                EventType.MESSAGE_RECEIVED,
                message_content,
                validation_result,
                error_details,
            )

        # Assert
        self.assertEqual(event.workflow_id, self.workflow_id)
        self.assertEqual(event.microservice_id, self.microservice_id)
        self.assertEqual(event.event_type, EventType.MESSAGE_RECEIVED)
        self.assertEqual(event.message_content, message_content)
        self.assertEqual(event.validation_result, validation_result)
        self.assertEqual(event.error_details, error_details)

    def test_initialization_with_managed_identity_credential(self):
        from azure_monitor_lib import AzureMonitorFactory
        insights_uami_client_id = "test-client-id-123"
        with patch.dict(
            os.environ,
            {
                "APPLICATIONINSIGHTS_CONNECTION_STRING": "InstrumentationKey=test-key;IngestionEndpoint=test-endpoint",
                "INSIGHTS_UAMI_CLIENT_ID": insights_uami_client_id,
            },
        ):
            with patch(
                "azure_monitor_lib.azure_monitor_factory.configure_azure_monitor"
            ) as mock_configure:
                with patch(
                    "azure_monitor_lib.azure_monitor_factory.ManagedIdentityCredential"
                ) as mock_managed_cred:
                    with patch(
                        "azure_monitor_lib.azure_monitor_factory.DefaultAzureCredential"
                    ) as mock_default_cred:
                        logger = EventLogger("test-workflow", "test-service", AzureMonitorFactory)

                        self.assertTrue(logger.azure_monitor_enabled)
                        mock_configure.assert_called_once()
                        mock_managed_cred.assert_called_once_with(
                            client_id=insights_uami_client_id
                        )
                        mock_default_cred.assert_not_called()

    def test_dependency_injection_with_custom_factory(self):
        """Test that EventLogger uses the injected factory instead of the global one."""
        from unittest.mock import MagicMock

        # Create a mock factory
        mock_factory = MagicMock()
        mock_factory.is_enabled.return_value = True
        mock_factory.ensure_initialized.return_value = True

        # Create EventLogger with injected factory
        logger = EventLogger("test-workflow", "test-service", azure_monitor_factory=mock_factory)

        # Verify the injected factory was used
        mock_factory.is_enabled.assert_called_once()
        mock_factory.ensure_initialized.assert_called_once()

        # Verify the injected factory is stored
        self.assertEqual(logger._azure_monitor_factory, mock_factory)
        self.assertTrue(logger.azure_monitor_enabled)

    def test_initialization_with_default_credential_scenarios(self):
        test_cases = [
            {
                "name": "INSIGHTS_UAMI_CLIENT_ID not set",
                "insights_uami_client_id": None,
            },
            {"name": "INSIGHTS_UAMI_CLIENT_ID is empty", "insights_uami_client_id": ""},
            {
                "name": "INSIGHTS_UAMI_CLIENT_ID is whitespace",
                "insights_uami_client_id": "   ",
            },
        ]

        for case in test_cases:
            with self.subTest(msg=case["name"]):
                from azure_monitor_lib import AzureMonitorFactory
                # Reset factory state for each subtest
                AzureMonitorFactory._initialized = False
                AzureMonitorFactory._meter = None
                AzureMonitorFactory._is_enabled = None
                AzureMonitorFactory._connection_string = None
                AzureMonitorFactory._uami_client_id = None

                env_vars = {
                    "APPLICATIONINSIGHTS_CONNECTION_STRING": "InstrumentationKey=test-key;IngestionEndpoint=test-endpoint",
                }
                if case["insights_uami_client_id"] is not None:
                    env_vars["INSIGHTS_UAMI_CLIENT_ID"] = case[
                        "insights_uami_client_id"
                    ]

                # Use clear=True to start with a clean environment for each subtest
                with patch.dict(os.environ, env_vars, clear=True):
                    with (
                        patch(
                            "azure_monitor_lib.azure_monitor_factory.configure_azure_monitor"
                        ) as mock_configure,
                        patch(
                            "azure_monitor_lib.azure_monitor_factory.ManagedIdentityCredential"
                        ) as mock_managed_cred,
                        patch(
                            "azure_monitor_lib.azure_monitor_factory.DefaultAzureCredential"
                        ) as mock_default_cred,
                    ):
                        logger = EventLogger("test-workflow", "test-service", AzureMonitorFactory)

                        self.assertTrue(logger.azure_monitor_enabled)
                        mock_configure.assert_called_once()
                        mock_default_cred.assert_called_once()
                        mock_managed_cred.assert_not_called()


if __name__ == "__main__":
    unittest.main()
