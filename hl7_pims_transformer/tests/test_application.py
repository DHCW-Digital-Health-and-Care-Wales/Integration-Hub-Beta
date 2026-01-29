import unittest
from typing import Any
from unittest.mock import MagicMock, patch

from azure.servicebus import ServiceBusMessage
from hl7apy.parser import parse_message
from transformer_base_lib.message_processor import process_message

from hl7_pims_transformer.app_config import AppConfig
from hl7_pims_transformer.pims_transformer import PimsTransformer
from tests.pims_messages import pims_messages


class TestProcessPimsMessage(unittest.TestCase):
    def setUp(self) -> None:
        self.hl7_string = pims_messages["a40"]
        self.hl7_message = parse_message(self.hl7_string)
        self.service_bus_message = ServiceBusMessage(body=self.hl7_string)

        self.transformer = PimsTransformer()

        self.mock_sender = MagicMock()
        self.mock_event_logger = MagicMock()

        self.process_message_kwargs = {
            "sender_client": self.mock_sender,
            "event_logger": self.mock_event_logger,
            "transform": self.transformer.transform_message,
            "transformer_display_name": "PIMS",
            "received_audit_text": self.transformer.get_received_audit_text(),
            "processed_audit_text_builder": self.transformer.get_processed_audit_text,
            "failed_audit_text": "PIMS transformation failed",
        }

        self.mock_transformed_message = MagicMock()
        self.mock_transformed_message.to_er7.return_value = (
            "MSH|^~\\&|103|103|200|200|20250806100245||ADT|73711860|P|2.5|||||GBR||EN\r"
        )

        self.mock_app_config = AppConfig(
            None,
            None,
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

    @patch("hl7_pims_transformer.pims_transformer.transform_pims_message")
    def test_process_message_successfully_sends_message(self, mock_transform_pims: Any) -> None:
        mock_transform_pims.return_value = self.mock_transformed_message
        expected_message = self.mock_transformed_message.to_er7.return_value

        result = process_message(self.service_bus_message, **self.process_message_kwargs)

        self.assertTrue(result)
        mock_transform_pims.assert_called_once()
        self.mock_sender.send_message.assert_called_once_with(expected_message, custom_properties=None)
        self.mock_event_logger.log_message_received.assert_called_once()
        self.mock_event_logger.log_message_processed.assert_called_once_with(
            self.hl7_string, "PIMS transformation applied for SENDING_APP: PIMS"
        )
        self.mock_event_logger.log_message_failed.assert_not_called()

    @patch("hl7_pims_transformer.pims_transformer.transform_pims_message")
    def test_process_message_transform_failure(self, mock_transform_pims: Any) -> None:
        error_reason = "Invalid segment mapping"
        mock_transform_pims.side_effect = ValueError(error_reason)

        result = process_message(self.service_bus_message, **self.process_message_kwargs)

        self.assertFalse(result)
        self.mock_sender.send_message.assert_not_called()

    @patch("hl7_pims_transformer.pims_transformer.transform_pims_message")
    def test_process_message_audit_logging_failure(self, mock_transform_pims: Any) -> None:
        error_reason = "Invalid segment mapping"
        mock_transform_pims.side_effect = ValueError(error_reason)

        process_message(self.service_bus_message, **self.process_message_kwargs)

        self.mock_event_logger.log_message_received.assert_called_once_with(
            self.hl7_string, "Message received for PIMS transformation"
        )
        self.mock_event_logger.log_message_failed.assert_called_once_with(
            self.hl7_string,
            f"Failed to transform PIMS message: {error_reason}",
            "PIMS transformation failed",
        )
        self.mock_event_logger.log_message_processed.assert_not_called()

    @patch("hl7_pims_transformer.pims_transformer.transform_pims_message")
    def test_process_message_unexpected_error(self, mock_transform_pims: Any) -> None:
        error_reason = "Unexpected database connection error"
        mock_transform_pims.side_effect = Exception(error_reason)

        result = process_message(self.service_bus_message, **self.process_message_kwargs)

        self.assertFalse(result)
