import unittest
from typing import Any
from unittest.mock import MagicMock, patch

from azure.servicebus import ServiceBusMessage
from hl7apy.parser import parse_message

from hl7_chemo_transformer.app_config import AppConfig
from hl7_chemo_transformer.application import _get_sending_app, _process_message, main

TEST_HL7_MESSAGE_SOUTHWEST_A31 = (
    "MSH|^~\\&|192|192|200|200|20250624161510||ADT^A31|369913945290925|P|2.4|||NE|NE\r"
    "EVN|Sub|20250624161510\r"
    "PID|1|1000000001^^^^NH|1000000001^^^^NH~B1000001^^^^PAS||TEST^TEST^^^Mrs.||20000101000000|F|||1 TEST TEST TEST TEST^TEST^TEST^TEST^CF11 9AD||01000 000001^PRN|01000 000001^WPN||||||||||||||||||1\r"
    "PD1||||G7000001\r"
    "PV1||U\r"
    "NK1|1|Test^Tom^F|GRD^Guardian^HL70063\r"
)

TEST_HL7_MESSAGE_VEL_A28 = (
    "MSH|^~\\&|224|224|200|200|20250701154910||ADT^A28|474997159036153|P|2.4|||NE|NE\r"
    "EVN|Sub|20250701154910\r"
    "PID|1|1000000002^^^^NH|1000002^^^^PAS~1000000002^^^^NH||SAMPLE^PATIENT^TEST^^Mr.||19950515000000|M|||222, SAMPLE STREET^TESTVILLE^TESTSTATE^^CF22 8BD||01000 000002^PRN^^sample@test.com~07000000002^PRS|07000000002^WPN||||||||||||||||||1\r"
    "PD1||||G7000002\r"
    "PV1||U\r"
    "NK1|1|Test^Tom^F|GRD^Guardian^HL70063\r"
)


class TestProcessMessageIntegration(unittest.TestCase):
    def setUp(self) -> None:
        self.hl7_string = TEST_HL7_MESSAGE_SOUTHWEST_A31
        self.hl7_message = parse_message(self.hl7_string)
        self.service_bus_message = ServiceBusMessage(body=self.hl7_string)
        self.mock_sender = MagicMock()
        self.mock_audit_client = MagicMock()

    def test_process_message_real_transformation_success(self) -> None:
        result = _process_message(self.service_bus_message, self.mock_sender, self.mock_audit_client)

        self.assertTrue(result.success)
        self.mock_sender.send_message.assert_called_once()

        sent_message = self.mock_sender.send_message.call_args[0][0]
        self.assertIn("ADT^A31^ADT_A05", sent_message)
        self.assertIn("2.5", sent_message)

    def test_process_message_real_transformation_audit_logging(self) -> None:
        _process_message(self.service_bus_message, self.mock_sender, self.mock_audit_client)

        self.mock_audit_client.log_message_received.assert_called_once_with(
            self.hl7_string, "Message received for Chemocare transformation"
        )
        self.mock_audit_client.log_message_processed.assert_called_once_with(
            self.hl7_string,
            "Chemocare transformation applied for SENDING_APP: 192",
        )

    def test_process_message_different_message_types_real_transformer(self) -> None:
        test_cases = [
            (TEST_HL7_MESSAGE_SOUTHWEST_A31, "192", "ADT^A31^ADT_A05", "Southwest A31"),
            (TEST_HL7_MESSAGE_VEL_A28, "224", "ADT^A28^ADT_A05", "VEL A28"),
        ]

        for hl7_string, expected_sending_app, expected_msg_type, description in test_cases:
            with self.subTest(description=description):
                service_bus_message = ServiceBusMessage(body=hl7_string)
                mock_sender = MagicMock()
                mock_audit_client = MagicMock()

                result = _process_message(service_bus_message, mock_sender, mock_audit_client)

                self.assertTrue(result.success)
                sent_message = mock_sender.send_message.call_args[0][0]
                self.assertIn(expected_msg_type, sent_message)
                self.assertIn("2.5", sent_message)


class TestProcessMessageUnit(unittest.TestCase):
    def setUp(self) -> None:
        self.hl7_string = TEST_HL7_MESSAGE_SOUTHWEST_A31
        self.hl7_message = parse_message(self.hl7_string)
        self.service_bus_message = ServiceBusMessage(body=self.hl7_string)
        self.mock_sender = MagicMock()
        self.mock_audit_client = MagicMock()

        self.mock_transformed_message = MagicMock()
        self.mock_transformed_message.to_er7.return_value = (
            "MSH|^~\\&|TRANSFORMED|192|200|200|20250624161510||ADT^A31|369913945290925|P|2.5|||NE|NE\r"
        )

    @patch("hl7_chemo_transformer.application.transform_chemocare_message")
    def test_process_message_input_validation(self, mock_transform_chemocare: Any) -> None:
        mock_transform_chemocare.return_value = self.mock_transformed_message

        result = _process_message(self.service_bus_message, self.mock_sender, self.mock_audit_client)

        mock_transform_chemocare.assert_called_once()
        input_message = mock_transform_chemocare.call_args[0][0]
        self.assertEqual(input_message.msh.msh_10.value, "369913945290925")
        self.assertTrue(result.success)

    @patch("hl7_chemo_transformer.application.transform_chemocare_message")
    def test_process_message_transform_failure(self, mock_transform_chemocare: Any) -> None:
        error_reason = "Invalid segment mapping"
        mock_transform_chemocare.side_effect = ValueError(error_reason)

        result = _process_message(self.service_bus_message, self.mock_sender, self.mock_audit_client)

        self.assertFalse(result.success)
        self.assertEqual(result.error_reason, error_reason)
        self.mock_sender.send_message.assert_not_called()

    @patch("hl7_chemo_transformer.application.transform_chemocare_message")
    def test_process_message_audit_logging_failure(self, mock_transform_chemocare: Any) -> None:
        error_reason = "Invalid segment mapping"
        mock_transform_chemocare.side_effect = ValueError(error_reason)

        _process_message(self.service_bus_message, self.mock_sender, self.mock_audit_client)

        self.mock_audit_client.log_message_received.assert_called_once_with(
            self.hl7_string, "Message received for Chemocare transformation"
        )
        self.mock_audit_client.log_message_failed.assert_called_once_with(
            self.hl7_string,
            f"Failed to transform Chemocare message: {error_reason}",
            "Chemocare transformation failed",
        )
        self.mock_audit_client.log_message_processed.assert_not_called()

    @patch("hl7_chemo_transformer.application.transform_chemocare_message")
    def test_process_message_unexpected_error(self, mock_transform_chemocare: Any) -> None:
        error_reason = "Unexpected database connection error"
        mock_transform_chemocare.side_effect = Exception(error_reason)

        result = _process_message(self.service_bus_message, self.mock_sender, self.mock_audit_client)

        self.assertFalse(result.success)
        self.assertEqual(result.error_reason, error_reason)
        self.assertTrue(result.retry)


class TestGetSendingApp(unittest.TestCase):
    def setUp(self) -> None:
        self.test_cases = [
            (TEST_HL7_MESSAGE_SOUTHWEST_A31, "192", "Southwest A31"),
            (TEST_HL7_MESSAGE_VEL_A28, "224", "VEL A28"),
        ]

    def test_get_sending_app_all_message_types(self) -> None:
        for hl7_string, expected_sending_app, description in self.test_cases:
            with self.subTest(description=description):
                hl7_message = parse_message(hl7_string)

                sending_app = _get_sending_app(hl7_message)

                self.assertEqual(sending_app, expected_sending_app)


class TestMainApplication(unittest.TestCase):
    def setUp(self) -> None:
        """Setup for main application tests"""
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

    @patch("hl7_chemo_transformer.application.AuditServiceClient")
    @patch("hl7_chemo_transformer.application.AppConfig")
    @patch("hl7_chemo_transformer.application.ServiceBusClientFactory")
    @patch("hl7_chemo_transformer.application.TCPHealthCheckServer")
    def test_health_check_server_lifecycle(
        self, mock_health_check: Any, mock_factory: Any, mock_app_config: Any, mock_audit_client: Any
    ) -> None:
        mock_health_server = MagicMock()
        mock_health_check_ctx = MagicMock()
        mock_health_check_ctx.__enter__.return_value = mock_health_server
        mock_health_check.return_value = mock_health_check_ctx
        mock_app_config.read_env_config.return_value = self.mock_app_config

        with patch("hl7_chemo_transformer.application.PROCESSOR_RUNNING", False):
            main()

        mock_health_check.assert_called_once_with("localhost", 9000)
        mock_health_server.start.assert_called_once()
        mock_health_check_ctx.__exit__.assert_called_once()


if __name__ == "__main__":
    unittest.main()
