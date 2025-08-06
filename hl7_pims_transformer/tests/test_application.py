import unittest
from typing import Any
from unittest.mock import MagicMock, patch

from azure.servicebus import ServiceBusMessage
from hl7apy.parser import parse_message

from hl7_pims_transformer.app_config import AppConfig
from hl7_pims_transformer.application import _process_message
from tests.pims_messages import pims_messages


class TestProcessPimsMessage(unittest.TestCase):
    def setUp(self) -> None:
        self.hl7_string = pims_messages["a40"]
        self.hl7_message = parse_message(self.hl7_string)
        self.service_bus_message = ServiceBusMessage(body=self.hl7_string)

        self.mock_sender = MagicMock()
        self.mock_audit_client = MagicMock()

        self.mock_transformed_message = MagicMock()
        self.mock_transformed_message.to_er7.return_value = (
            "MSH|^~\\&|TRANSFORMED|192|200|200|20250624161510||ADT^A31|369913945290925|P|2.5|||NE|NE\r"
        )

        self.mock_app_config = AppConfig(
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            health_check_hostname="localhost",
            health_check_port=9000,
        )

    @patch("hl7_pims_transformer.application.transform_pims_message")
    def test_process_message_input_validation(self, mock_transform_pims: Any) -> None:
        mock_transform_pims.return_value = self.mock_transformed_message

        result = _process_message(self.service_bus_message, self.mock_sender, self.mock_audit_client)

        mock_transform_pims.assert_called_once()
        input_message = mock_transform_pims.call_args[0][0]
        self.assertEqual(input_message.msh.msh_10.value, "73711860")
        self.assertTrue(result.success)

    @patch("hl7_pims_transformer.application.transform_pims_message")
    def test_process_message_transform_failure(self, mock_transform_pims: Any) -> None:
        error_reason = "Invalid segment mapping"
        mock_transform_pims.side_effect = ValueError(error_reason)

        result = _process_message(self.service_bus_message, self.mock_sender, self.mock_audit_client)

        self.assertFalse(result.success)
        self.assertEqual(result.error_reason, error_reason)
        self.mock_sender.send_message.assert_not_called()

    @patch("hl7_pims_transformer.application.transform_pims_message")
    def test_process_message_audit_logging_failure(self, mock_transform_pims: Any) -> None:
        error_reason = "Invalid segment mapping"
        mock_transform_pims.side_effect = ValueError(error_reason)

        _process_message(self.service_bus_message, self.mock_sender, self.mock_audit_client)

        self.mock_audit_client.log_message_received.assert_called_once_with(
            self.hl7_string, "Message received for PIMS transformation"
        )
        self.mock_audit_client.log_message_failed.assert_called_once_with(
            self.hl7_string,
            f"Failed to transform PIMS message: {error_reason}",
            "PIMS transformation failed",
        )
        self.mock_audit_client.log_message_processed.assert_not_called()

    @patch("hl7_pims_transformer.application.transform_pims_message")
    def test_process_message_unexpected_error(self, mock_transform_pims: Any) -> None:
        error_reason = "Unexpected database connection error"
        mock_transform_pims.side_effect = Exception(error_reason)

        result = _process_message(self.service_bus_message, self.mock_sender, self.mock_audit_client)

        self.assertFalse(result.success)
        self.assertEqual(result.error_reason, error_reason)
        self.assertTrue(result.retry)
