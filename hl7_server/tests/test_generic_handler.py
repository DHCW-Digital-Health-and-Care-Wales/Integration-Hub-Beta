import unittest
from unittest.mock import ANY, MagicMock, patch

from hl7_validation import XmlValidationError

from hl7_server.generic_handler import GenericHandler
from hl7_server.hl7_validator import HL7Validator, ValidationException

# Sample valid HL7 message (pipe & hat, type A28)
VALID_A28_MESSAGE = (
    "MSH|^~\\&|252|252|100|100|2025-05-05 23:23:32||ADT^A31^ADT_A05|202505052323364444|P|2.5|||||GBR||EN\r"
    "PID|1||123456^^^Hospital^MR||Doe^John\r"
)

VALID_MPI_OUTBOUND_MESSAGE_WITH_UPDATE_SOURCE = (
    "MSH|^~\\&|252|252|100|100|2025-05-05 23:23:32||ADT^A28^ADT_A05|202505052323364444|P|2.5|||||GBR||EN\r"
    "PID|1|98765^^^108^MR|1000000001^^^NHS^NH~BCUCC1000000001^^^212^PI||"
    "TEST^TEST^T^^Mrs.||20000101000000|F|||TEST,^TEST^TEST TEST^^CF11 9AD||"
    "01000 000 001|07000000001|||||||||||||||2023-01-15|||0\r"
)

INVALID_MPI_OUTBOUND_MESSAGE_TYPE = (
    "MSH|^~\\&|252|252|100|100|2025-05-05 23:23:32||ADT^A01^ADT_A01|202505052323364444|P|2.5|||||GBR||EN\r"
    "PID|1|98765^^^108^MR||Doe^John\r"
)

ACK_BUILDER_ATTRIBUTE = "hl7_server.generic_handler.HL7AckBuilder"


class TestGenericHandler(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_sender = MagicMock()
        self.mock_event_logger = MagicMock()
        self.mock_metric_sender = MagicMock()
        self.mock_message_store = MagicMock()
        self.validator = MagicMock()
        self.handler = GenericHandler(
            VALID_A28_MESSAGE,
            self.mock_sender,
            self.mock_event_logger,
            self.mock_metric_sender,
            self.validator,
            workflow_id="test-workflow",
            sending_app="252",
            message_store_client=self.mock_message_store,
        )

    def test_valid_a28_message_returns_ack(self) -> None:
        with patch(ACK_BUILDER_ATTRIBUTE) as mock_builder:
            mock_instance = mock_builder.return_value
            mock_ack_message = MagicMock()
            mock_ack_message.to_mllp.return_value = "\x0bACK_CONTENT\x1c\r"
            mock_instance.build_ack.return_value = mock_ack_message
            result = self.handler.reply()

            mock_instance.build_ack.assert_called_once()
            self.assertIn("ACK_CONTENT", result)

    def test_ack_message_created_correctly(self) -> None:
        with patch(ACK_BUILDER_ATTRIBUTE) as MockAckBuilder:
            mock_builder_instance = MockAckBuilder.return_value

            # Mock the Message-like object returned from build_ack
            mock_ack_message = MagicMock()
            mock_ack_message.to_mllp.return_value = (
                "\x0bMSH|^~\\&|100|100|252|252|202405280830||ACK^A28^ACK|123456|P|2.5\rMSA|AA|123456\r\x1c\r"
            )
            mock_builder_instance.build_ack.return_value = mock_ack_message

            ack_response = self.handler.reply()

            self.assertIn("MSA|AA|123456", ack_response)
            self.assertIn("ACK^A28^ACK", ack_response)
            self.assertTrue(ack_response.startswith("\x0b"))
            self.assertTrue(ack_response.endswith("\x1c\r"))

            mock_builder_instance.build_ack.assert_called_once_with("202505052323364444", ANY)
            mock_ack_message.to_mllp.assert_called_once()

    @patch("hl7_server.generic_handler.logger")
    def test_validation_exception(self, mock_logger: MagicMock) -> None:
        exception = ValidationException("Invalid sending app id")
        message = "MSH|^~\\&|100|100|100|252|202405280830||ACK^A28^ACK|123456|P|2.5\r"

        validator = MagicMock()
        validator.validate = MagicMock(side_effect=exception)
        handler = GenericHandler(
            message,
            self.mock_sender,
            self.mock_event_logger,
            self.mock_metric_sender,
            validator,
            workflow_id="test-workflow",
            sending_app="252",
            message_store_client=self.mock_message_store,
        )

        with self.assertRaises(ValidationException):
            handler.reply()

        mock_logger.error.assert_called_once_with(f"HL7 validation error: {exception}")
        self.mock_event_logger.log_message_failed.assert_called_once_with(message, f"HL7 validation error: {exception}")

    def test_message_sent_to_service_bus(self) -> None:
        self.handler.reply()

        call_args = self.mock_sender.send_text_message.call_args
        self.assertEqual(call_args[0][0], VALID_A28_MESSAGE)
        tracking_metadata_properties = call_args[0][1]
        self.assertIsNotNone(tracking_metadata_properties)
        self.assertIn("MessageReceivedAt", tracking_metadata_properties)
        self.assertIn("CorrelationId", tracking_metadata_properties)
        self.assertEqual(tracking_metadata_properties["WorkflowID"], "test-workflow")
        self.assertEqual(tracking_metadata_properties["SourceSystem"], "252")

    @patch(
        "hl7_server.generic_handler.FLOW_PROPERTY_BUILDERS",
        {"mpi": lambda msg: (_ for _ in ()).throw(Exception("boom"))},
    )
    def test_flow_property_builder_failure_does_not_prevent_tracking_metadata(self) -> None:
        validator = HL7Validator(flow_name="mpi")
        handler = GenericHandler(
            VALID_MPI_OUTBOUND_MESSAGE_WITH_UPDATE_SOURCE,
            self.mock_sender,
            self.mock_event_logger,
            self.mock_metric_sender,
            validator,
            workflow_id="test-workflow",
            sending_app="252",
            message_store_client=self.mock_message_store,
            flow_name="mpi",
        )

        handler.reply()

        call_args = self.mock_sender.send_text_message.call_args
        tracking_metadata_properties = call_args[0][1]
        self.assertIn("MessageReceivedAt", tracking_metadata_properties)
        self.assertIn("CorrelationId", tracking_metadata_properties)
        self.assertEqual(tracking_metadata_properties["WorkflowID"], "test-workflow")
        self.assertEqual(tracking_metadata_properties["SourceSystem"], "252")

    @patch("hl7_server.generic_handler.validate_and_convert_parsed_message_with_flow_schema")
    def test_mpi_outbound_flow_sets_tracking_metadata_with_update_source(
        self, mock_validate_flow_xml: MagicMock
    ) -> None:
        validator = HL7Validator(flow_name="mpi")
        with patch(ACK_BUILDER_ATTRIBUTE) as mock_builder:
            mock_ack_instance = mock_builder.return_value
            mock_ack_message = MagicMock()
            mock_ack_message.to_mllp.return_value = "\x0bACK\x1c\r"
            mock_ack_instance.build_ack.return_value = mock_ack_message

            handler = GenericHandler(
                VALID_MPI_OUTBOUND_MESSAGE_WITH_UPDATE_SOURCE,
                self.mock_sender,
                self.mock_event_logger,
                self.mock_metric_sender,
                validator,
                workflow_id="test-workflow",
                sending_app="252",
                message_store_client=self.mock_message_store,
                flow_name="mpi",
            )

            handler.reply()

        mock_validate_flow_xml.assert_not_called()
        call_args = self.mock_sender.send_text_message.call_args
        self.assertEqual(call_args[0][0], VALID_MPI_OUTBOUND_MESSAGE_WITH_UPDATE_SOURCE)
        tracking_metadata_properties = call_args[0][1]
        self.assertIn("MessageReceivedAt", tracking_metadata_properties)
        self.assertIn("CorrelationId", tracking_metadata_properties)
        self.assertEqual(tracking_metadata_properties["WorkflowID"], "test-workflow")
        self.assertEqual(tracking_metadata_properties["SourceSystem"], "252")
        self.assertEqual(tracking_metadata_properties["MessageType"], "A28")
        self.assertEqual(tracking_metadata_properties["UpdateSources"], "|108|")
        self.assertEqual(tracking_metadata_properties["AssigningAuthorities"], "|NHS|212|")
        self.assertEqual(tracking_metadata_properties["DateDeath"], "2023-01-15")
        self.assertEqual(tracking_metadata_properties["ReasonDeath"], "")

    @patch("hl7_server.generic_handler.validate_and_convert_parsed_message_with_flow_schema")
    def test_mpi_outbound_flow_rejects_invalid_messages(self, mock_validate_flow_xml: MagicMock) -> None:
        exception_scenarios = [
            ("unsupported_message_type", INVALID_MPI_OUTBOUND_MESSAGE_TYPE),
            ("missing_update_source", VALID_MPI_OUTBOUND_MESSAGE_WITH_UPDATE_SOURCE.splitlines()[0]),
        ]

        for name, message in exception_scenarios:
            with self.subTest(scenario=name):
                validator = HL7Validator(flow_name="mpi")

                handler = GenericHandler(
                    message,
                    self.mock_sender,
                    self.mock_event_logger,
                    self.mock_metric_sender,
                    validator,
                    workflow_id="test-workflow",
                    sending_app="252",
                    message_store_client=self.mock_message_store,
                    flow_name="mpi",
                )

                with self.assertRaises(ValidationException):
                    handler.reply()

                mock_validate_flow_xml.assert_not_called()
                self.mock_sender.send_text_message.assert_not_called()

                mock_validate_flow_xml.reset_mock()

    def test_metric_sent_on_message_received(self) -> None:
        self.handler.reply()

        self.mock_metric_sender.send_message_received_metric.assert_called_once()

    @patch("hl7_server.generic_handler.validate_parsed_message_with_standard")
    def test_standard_validation_called_when_version_set(self, mock_validate_standard: MagicMock) -> None:
        with patch(ACK_BUILDER_ATTRIBUTE) as mock_builder:
            mock_ack_instance = mock_builder.return_value
            mock_ack_message = MagicMock()
            mock_ack_message.to_mllp.return_value = "\x0bACK\x1c\r"
            mock_ack_instance.build_ack.return_value = mock_ack_message

            handler = GenericHandler(
                VALID_A28_MESSAGE,
                self.mock_sender,
                self.mock_event_logger,
                self.mock_metric_sender,
                self.validator,
                workflow_id="test-workflow",
                sending_app="252",
                message_store_client=self.mock_message_store,
                standard_version="2.5",
            )

            handler.reply()

        mock_validate_standard.assert_called_once_with(ANY, "2.5")
        self.mock_event_logger.log_validation_result.assert_any_call(
            VALID_A28_MESSAGE,
            "Standard HL7 v2.5 validation passed",
            is_success=True,
        )

    @patch("hl7_server.generic_handler.validate_parsed_message_with_standard")
    @patch("hl7_server.generic_handler.logger")
    def test_standard_validation_failure_logs_and_raises(
        self, mock_logger: MagicMock, mock_validate_standard: MagicMock
    ) -> None:
        mock_validate_standard.side_effect = XmlValidationError("Standard HL7 v2.5 validation failed: Missing PV1")

        handler = GenericHandler(
            VALID_A28_MESSAGE,
            self.mock_sender,
            self.mock_event_logger,
            self.mock_metric_sender,
            self.validator,
            workflow_id="test-workflow",
            sending_app="252",
            message_store_client=self.mock_message_store,
            standard_version="2.5",
        )

        with self.assertRaises(XmlValidationError):
            handler.reply()

        mock_logger.error.assert_called()
        standard_validation_calls = self.mock_event_logger.log_validation_result.call_args_list
        self.assertTrue(
            any(
                call.args[0] == VALID_A28_MESSAGE
                and call.args[1].startswith("Standard validation error: Standard HL7 v2.5 validation failed")
                and call.kwargs.get("is_success") is False
                and call.kwargs.get("correlation_id") is not None
                for call in standard_validation_calls
            )
        )
        self.assertEqual(self.mock_event_logger.log_message_failed.call_count, 2)
        self.mock_sender.send_text_message.assert_not_called()

    @patch("hl7_server.generic_handler.validate_parsed_message_with_standard")
    @patch("hl7_server.generic_handler.validate_and_convert_parsed_message_with_flow_schema")
    def test_both_flow_and_standard_validation_called(
        self, mock_validate_flow: MagicMock, mock_validate_standard: MagicMock
    ) -> None:
        with patch(ACK_BUILDER_ATTRIBUTE) as mock_builder:
            mock_ack_instance = mock_builder.return_value
            mock_ack_message = MagicMock()
            mock_ack_message.to_mllp.return_value = "\x0bACK\x1c\r"
            mock_ack_instance.build_ack.return_value = mock_ack_message

            handler = GenericHandler(
                VALID_A28_MESSAGE,
                self.mock_sender,
                self.mock_event_logger,
                self.mock_metric_sender,
                self.validator,
                workflow_id="test-workflow",
                sending_app="252",
                message_store_client=self.mock_message_store,
                flow_name="phw",
                standard_version="2.5",
            )

            handler.reply()

        mock_validate_flow.assert_called_once_with(ANY, VALID_A28_MESSAGE, "phw")
        mock_validate_standard.assert_called_once_with(ANY, "2.5")

    @patch("hl7_server.generic_handler.validate_parsed_message_with_standard")
    def test_standard_validation_not_called_when_version_not_set(self, mock_validate_standard: MagicMock) -> None:
        with patch(ACK_BUILDER_ATTRIBUTE) as mock_builder:
            mock_ack_instance = mock_builder.return_value
            mock_ack_message = MagicMock()
            mock_ack_message.to_mllp.return_value = "\x0bACK\x1c\r"
            mock_ack_instance.build_ack.return_value = mock_ack_message

            handler = GenericHandler(
                VALID_A28_MESSAGE,
                self.mock_sender,
                self.mock_event_logger,
                self.mock_metric_sender,
                self.validator,
                workflow_id="test-workflow",
                sending_app="252",
                message_store_client=self.mock_message_store,
            )

            handler.reply()

        mock_validate_standard.assert_not_called()

    def test_message_sent_to_message_store(self) -> None:
        self.handler.reply()

        self.mock_message_store.send_to_store.assert_called_once()
        call_kwargs = self.mock_message_store.send_to_store.call_args
        self.assertEqual(call_kwargs.kwargs["raw_payload"], VALID_A28_MESSAGE)
        self.assertIn("message_received_at", call_kwargs.kwargs)
        self.assertIn("correlation_id", call_kwargs.kwargs)
        self.assertIn("source_system", call_kwargs.kwargs)

    def test_message_stored_before_service_bus_send(self) -> None:
        message_stored = {"value": False}

        def _store_side_effect(*args: object, **kwargs: object) -> None:
            message_stored["value"] = True

        def _send_side_effect(*args: object, **kwargs: object) -> None:
            self.assertTrue(message_stored["value"], "Message should be stored before sending to Service Bus")

        self.mock_message_store.send_to_store.side_effect = _store_side_effect
        self.mock_sender.send_text_message.side_effect = _send_side_effect

        self.handler.reply()

        self.mock_message_store.send_to_store.assert_called_once()
        self.mock_sender.send_text_message.assert_called_once()

    @patch("hl7_server.generic_handler.logger")
    def test_message_store_failure_does_not_block_ack(self, mock_logger: MagicMock) -> None:
        self.mock_message_store.send_to_store.side_effect = Exception("Store unavailable")

        # Should still return ACK without raising
        result = self.handler.reply()
        self.assertIsNotNone(result)

        mock_logger.error.assert_any_call(
            "Failed to send to message store: %s", self.mock_message_store.send_to_store.side_effect
        )

    @patch("hl7_server.generic_handler.convert_er7_to_xml")
    @patch("hl7_server.generic_handler.logger")
    def test_xml_payload_generation_failure_logs_error_and_emits_event(
        self, mock_logger: MagicMock, mock_convert_xml: MagicMock
    ) -> None:
        mock_convert_xml.side_effect = Exception("Bad HL7")

        result = self.handler.reply()

        self.assertIsNotNone(result)
        self.assertTrue(
            any(
                call.args and call.args[0].startswith("Failed to generate XML payload for message store: Bad HL7")
                for call in mock_logger.error.call_args_list
            )
        )
        xml_failure_calls = self.mock_event_logger.log_validation_result.call_args_list
        self.assertTrue(
            any(
                call.args[0] == VALID_A28_MESSAGE
                and call.args[1].startswith("Failed to generate XML payload for message store: Bad HL7")
                and call.kwargs.get("is_success") is False
                and call.kwargs.get("correlation_id") is not None
                for call in xml_failure_calls
            )
        )
        self.mock_message_store.send_to_store.assert_called_once()
        self.assertIsNone(self.mock_message_store.send_to_store.call_args.kwargs["xml_payload"])

    @patch("hl7_server.generic_handler.validate_and_convert_parsed_message_with_flow_schema")
    def test_flow_xml_validation_failure_sends_to_store_and_logs_correlation(
        self, mock_validate_flow: MagicMock
    ) -> None:
        validation_result = MagicMock()
        validation_result.is_valid = False
        validation_result.error_message = "Schema mismatch"
        validation_result.xml_string = None
        mock_validate_flow.return_value = validation_result

        handler = GenericHandler(
            VALID_A28_MESSAGE,
            self.mock_sender,
            self.mock_event_logger,
            self.mock_metric_sender,
            self.validator,
            workflow_id="test-workflow",
            sending_app="252",
            message_store_client=self.mock_message_store,
            flow_name="phw",
        )

        with self.assertRaises(XmlValidationError):
            handler.reply()

        self.mock_message_store.send_to_store.assert_called_once()
        failed_call_args = self.mock_event_logger.log_message_failed.call_args_list[0][0]
        self.assertIn("CorrelationId:", failed_call_args[1])


if __name__ == "__main__":
    unittest.main()
