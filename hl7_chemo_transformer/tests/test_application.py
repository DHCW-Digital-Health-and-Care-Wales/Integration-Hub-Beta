import unittest
from typing import Any
from unittest.mock import MagicMock, patch

from azure.servicebus import ServiceBusMessage
from hl7apy.parser import parse_message

from hl7_chemo_transformer.app_config import AppConfig
from hl7_chemo_transformer.application import ChemocareTransformer
from tests.chemo_messages import chemo_messages


class TestChemocareTransformer(unittest.TestCase):
    def setUp(self) -> None:
        self.hl7_string = chemo_messages["a31_southwest"]
        self.hl7_message = parse_message(self.hl7_string)
        self.service_bus_message = ServiceBusMessage(body=self.hl7_string)

        self.transformer = ChemocareTransformer()

        self.mock_sender = MagicMock()
        self.mock_event_logger = MagicMock()

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

    @patch("hl7_chemo_transformer.application.transform_chemocare_message")
    def test_transform_message_input_validation(self, mock_transform_chemocare: Any) -> None:
        mock_transform_chemocare.return_value = self.mock_transformed_message

        result = self.transformer.transform_message(self.hl7_message)

        mock_transform_chemocare.assert_called_once()
        input_message = mock_transform_chemocare.call_args[0][0]
        self.assertEqual(input_message.msh.msh_10.value, "369913945290925")
        self.assertEqual(result, self.mock_transformed_message)

    @patch("hl7_chemo_transformer.application.transform_chemocare_message")
    def test_transform_message_failure(self, mock_transform_chemocare: Any) -> None:
        error_reason = "Invalid segment mapping"
        mock_transform_chemocare.side_effect = ValueError(error_reason)

        with self.assertRaises(ValueError) as context:
            self.transformer.transform_message(self.hl7_message)

        self.assertEqual(str(context.exception), error_reason)

    def test_audit_text_methods(self) -> None:

        received_text = self.transformer.get_received_audit_text()
        self.assertEqual(received_text, "Message received for Chemocare transformation")

        failed_text = self.transformer.get_failed_audit_text()
        self.assertEqual(failed_text, "Chemocare transformation failed")

        processed_text = self.transformer.get_processed_audit_text(self.hl7_message)
        self.assertEqual(processed_text, "Chemocare transformation applied for SENDING_APP: 192")

    def test_transformer_initialization(self) -> None:
        transformer = ChemocareTransformer()
        self.assertEqual(transformer.transformer_name, "Chemocare")
        self.assertTrue(transformer.config_path.endswith("config.ini"))

    def test_get_sending_app_all_message_types(self) -> None:
        test_cases = [
            ("a31_southwest", "192", "Southwest A31"),
            ("a28_southwest", "192", "Southwest A28"),
            ("a31_vel", "224", "VEL A31"),
            ("a28_vel", "224", "VEL A28"),
            ("a31_southeast", "245", "Southeast A31"),
            ("a28_southeast", "245", "Southeast A28"),
            ("a28_bcu", "212", "BCU A28"),
            ("a31_bcu", "212", "BCU A31"),
        ]

        for message_key, expected_sending_app, description in test_cases:
            with self.subTest(description=description):
                hl7_message = parse_message(chemo_messages[message_key])

                sending_app = self.transformer._get_sending_app(hl7_message)

                self.assertEqual(sending_app, expected_sending_app)
