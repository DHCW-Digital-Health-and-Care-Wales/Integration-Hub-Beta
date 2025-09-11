import unittest
from typing import Any
from unittest.mock import MagicMock, patch

from azure.servicebus import ServiceBusMessage
from hl7apy.parser import parse_message

from hl7_pharmacy_transformer.app_config import AppConfig
from hl7_pharmacy_transformer.application import _get_assigning_authority, _process_message
from tests.pharmacy_messages import pharmacy_messages


class TestProcessPharmacyMessage(unittest.TestCase):
    def setUp(self) -> None:
        self.valid_hl7_string = pharmacy_messages["valid_assigning_authority_108"]
        self.valid_hl7_message = parse_message(self.valid_hl7_string)
        self.valid_service_bus_message = ServiceBusMessage(body=self.valid_hl7_string)

        self.invalid_hl7_string = pharmacy_messages["invalid_assigning_authority_999"]
        self.invalid_hl7_message = parse_message(self.invalid_hl7_string)
        self.invalid_service_bus_message = ServiceBusMessage(body=self.invalid_hl7_string)

        self.mock_sender = MagicMock()
        self.mock_event_logger = MagicMock()

        self.mock_transformed_message = MagicMock()
        self.mock_transformed_message.to_er7.return_value = (
            "MSH|^~\\&|TRANSFORMED|MPI|PHARMACY|MPI|20250624161510||ADT^A01|369913945290925|P|2.5|||NE|NE\r"
            "PID|||12345^^^108||DOE^JOHN\r"
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

    @patch("hl7_pharmacy_transformer.application.transform_pharmacy_message")
    def test_process_message_valid_assigning_authority(self, mock_transform_pharmacy: Any) -> None:
        mock_transform_pharmacy.return_value = self.mock_transformed_message

        result = _process_message(self.valid_service_bus_message, self.mock_sender, self.mock_event_logger)

        mock_transform_pharmacy.assert_called_once()
        input_message = mock_transform_pharmacy.call_args[0][0]
        self.assertEqual(input_message.msh.msh_10.value, "369913945290925")
        self.assertTrue(result)
        self.mock_sender.send_message.assert_called_once()

    @patch("hl7_pharmacy_transformer.application.transform_pharmacy_message")
    def test_process_message_invalid_assigning_authority(self, mock_transform_pharmacy: Any) -> None:
        mock_transform_pharmacy.side_effect = ValueError("Invalid assigning authority for Pharmacy system")

        result = _process_message(self.invalid_service_bus_message, self.mock_sender, self.mock_event_logger)

        self.assertFalse(result)
        self.mock_sender.send_message.assert_not_called()

    @patch("hl7_pharmacy_transformer.application.transform_pharmacy_message")
    def test_process_message_audit_logging_success(self, mock_transform_pharmacy: Any) -> None:
        mock_transform_pharmacy.return_value = self.mock_transformed_message

        _process_message(self.valid_service_bus_message, self.mock_sender, self.mock_event_logger)

        self.mock_event_logger.log_message_received.assert_called_once_with(
            self.valid_hl7_string, "Message received for Pharmacy transformation"
        )
        self.mock_event_logger.log_message_processed.assert_called_once()
        self.mock_event_logger.log_message_failed.assert_not_called()

    @patch("hl7_pharmacy_transformer.application.transform_pharmacy_message")
    def test_process_message_audit_logging_failure(self, mock_transform_pharmacy: Any) -> None:
        error_reason = "Invalid assigning authority for Pharmacy system"
        mock_transform_pharmacy.side_effect = ValueError(error_reason)

        _process_message(self.invalid_service_bus_message, self.mock_sender, self.mock_event_logger)

        self.mock_event_logger.log_message_received.assert_called_once_with(
            self.invalid_hl7_string, "Message received for Pharmacy transformation"
        )
        self.mock_event_logger.log_message_failed.assert_called_once_with(
            self.invalid_hl7_string,
            f"Failed to transform Pharmacy message: {error_reason}",
            "Pharmacy transformation failed",
        )
        self.mock_event_logger.log_message_processed.assert_not_called()

    @patch("hl7_pharmacy_transformer.application.transform_pharmacy_message")
    def test_process_message_unexpected_error(self, mock_transform_pharmacy: Any) -> None:
        error_reason = "Unexpected database connection error"
        mock_transform_pharmacy.side_effect = Exception(error_reason)

        result = _process_message(self.valid_service_bus_message, self.mock_sender, self.mock_event_logger)

        self.assertFalse(result)

    def test_get_assigning_authority_valid_cases(self) -> None:
        test_cases = [
            ("valid_assigning_authority_108", "108"),
            ("valid_assigning_authority_310", "310"),
        ]

        for message_key, expected_authority in test_cases:
            with self.subTest(message_key=message_key):
                hl7_message = parse_message(pharmacy_messages[message_key])
                assigning_authority = _get_assigning_authority(hl7_message)
                self.assertEqual(assigning_authority, expected_authority)

    def test_get_assigning_authority_invalid_cases(self) -> None:
        test_cases = [
            "invalid_assigning_authority_999",
            "missing_pid_segment",
            "missing_pid3_field",
            "empty_assigning_authority",
        ]

        for message_key in test_cases:
            with self.subTest(message_key=message_key):
                hl7_message = parse_message(pharmacy_messages[message_key])
                assigning_authority = _get_assigning_authority(hl7_message)
                self.assertEqual(assigning_authority, "UNKNOWN")
