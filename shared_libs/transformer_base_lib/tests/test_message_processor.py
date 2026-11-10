import unittest
from unittest.mock import MagicMock

from azure.servicebus import ServiceBusMessage

from transformer_base_lib.message_processor import process_message


class TestMessageProcessor(unittest.TestCase):
    def test_process_message_forwards_custom_properties(self) -> None:
        mock_sender = MagicMock()
        mock_event_logger = MagicMock()
        mock_transform = MagicMock()
        mock_transformed_msg = MagicMock()
        mock_transformed_msg.to_er7.return_value = b"MSH|^~\\&|...\r"
        mock_transform.return_value = mock_transformed_msg

        test_message_body = "MSH|^~\\&|252|252|100|100|2025-05-05 23:23:32||ADT^A31^ADT_A05|202505052323364444|P|2.5\r"
        test_properties = {
            "MessageReceivedAt": "2025-01-01T12:00:00+00:00",
            "CorrelationId": "123e4567-e89b-12d3-a456-426614174000",
            "WorkflowID": "test-workflow",
            "SourceSystem": "252",
        }

        mock_message = MagicMock(spec=ServiceBusMessage)
        mock_message.body = [test_message_body.encode("utf-8")]
        mock_message.application_properties = test_properties

        result = process_message(
            message=mock_message,
            sender_client=mock_sender,
            event_logger=mock_event_logger,
            transform=mock_transform,
            transformer_display_name="TestTransformer",
            received_audit_text="Test received",
            processed_audit_text_builder=lambda msg: "Test processed",
            failed_audit_text="Test failed",
        )

        self.assertTrue(result)
        mock_sender.send_message.assert_called_once()
        call_args = mock_sender.send_message.call_args
        self.assertEqual(call_args[0][0], mock_transformed_msg.to_er7.return_value)
        self.assertEqual(call_args[1]["custom_properties"], test_properties)

    def test_process_message_uses_egress_properties_builder(self) -> None:
        mock_sender = MagicMock()
        mock_transformed_msg = MagicMock()
        mock_transformed_msg.to_er7.return_value = b"MSH|^~\\&|...\r"
        mock_transform = MagicMock(return_value=mock_transformed_msg)
        builder = MagicMock(return_value={"MessageType": "A28"})

        mock_message = MagicMock(spec=ServiceBusMessage)
        mock_message.body = [b"MSH|^~\\&|252|252|100|100|2025-05-05 23:23:32||ADT^A04|1|P|2.5\r"]
        mock_message.application_properties = {"SourceSystem": "PIMS", "MessageType": "A04"}

        result = process_message(
            message=mock_message,
            sender_client=mock_sender,
            event_logger=MagicMock(),
            transform=mock_transform,
            transformer_display_name="TestTransformer",
            received_audit_text="Test received",
            processed_audit_text_builder=lambda msg: "Test processed",
            failed_audit_text="Test failed",
            egress_properties_builder=builder,
        )

        self.assertTrue(result)
        builder.assert_called_once_with({"SourceSystem": "PIMS", "MessageType": "A04"}, mock_transformed_msg)
        self.assertEqual(mock_sender.send_message.call_args[1]["custom_properties"], {"MessageType": "A28"})

    def test_process_message_handles_empty_properties(self) -> None:
        test_message_body = "MSH|^~\\&|252|252|100|100|2025-05-05 23:23:32||ADT^A31^ADT_A05|202505052323364444|P|2.5\r"
        empty_property_cases: list[dict[str, str] | None] = [None, {}]

        for empty_props in empty_property_cases:
            with self.subTest(empty_props=empty_props):
                mock_sender = MagicMock()
                mock_event_logger = MagicMock()
                mock_transform = MagicMock()
                mock_transformed_msg = MagicMock()
                mock_transformed_msg.to_er7.return_value = b"MSH|^~\\&|...\r"
                mock_transform.return_value = mock_transformed_msg

                mock_message = MagicMock(spec=ServiceBusMessage)
                mock_message.body = [test_message_body.encode("utf-8")]
                mock_message.application_properties = empty_props

                result = process_message(
                    message=mock_message,
                    sender_client=mock_sender,
                    event_logger=mock_event_logger,
                    transform=mock_transform,
                    transformer_display_name="TestTransformer",
                    received_audit_text="Test received",
                    processed_audit_text_builder=lambda msg: "Test processed",
                    failed_audit_text="Test failed",
                )

                self.assertTrue(result)
                mock_sender.send_message.assert_called_once()
                call_args = mock_sender.send_message.call_args
                self.assertEqual(call_args[1]["custom_properties"], None)

    def _build_message(self, body: str) -> MagicMock:
        mock_message = MagicMock(spec=ServiceBusMessage)
        mock_message.body = [body.encode("utf-8")]
        mock_message.application_properties = {"CorrelationId": "123e4567-e89b-12d3-a456-426614174000"}
        return mock_message

    def test_non_hl7_payload_is_parsed_and_serialised_with_custom_hooks(self) -> None:
        mock_sender = MagicMock()
        mock_event_logger = MagicMock()
        parse_input = MagicMock(return_value={"parsed": True})
        transform = MagicMock(return_value={"resourceType": "Bundle"})
        serialise_output = MagicMock(return_value='{"resourceType": "Bundle"}')
        audit_builder = MagicMock(return_value="Test processed")

        result = process_message(
            message=self._build_message("<Root><a>1</a></Root>"),
            sender_client=mock_sender,
            event_logger=mock_event_logger,
            transform=transform,
            transformer_display_name="TestTransformer",
            received_audit_text="Test received",
            processed_audit_text_builder=audit_builder,
            failed_audit_text="Test failed",
            parse_input=parse_input,
            serialise_output=serialise_output,
        )

        # A non-HL7 payload must never reach the HL7 parser, and the parsed object is what the hooks receive
        self.assertTrue(result)
        parse_input.assert_called_once_with("<Root><a>1</a></Root>")
        transform.assert_called_once_with({"parsed": True})
        audit_builder.assert_called_once_with({"parsed": True})
        serialise_output.assert_called_once_with({"resourceType": "Bundle"})
        self.assertEqual(mock_sender.send_message.call_args[0][0], '{"resourceType": "Bundle"}')
        self.assertEqual(mock_event_logger.log_message_processed.call_args[0][0], '{"resourceType": "Bundle"}')

    def test_parse_input_value_error_logs_failure_and_returns_false(self) -> None:
        mock_sender = MagicMock()
        mock_event_logger = MagicMock()
        transform = MagicMock()

        result = process_message(
            message=self._build_message("<Root>"),
            sender_client=mock_sender,
            event_logger=mock_event_logger,
            transform=transform,
            transformer_display_name="TestTransformer",
            received_audit_text="Test received",
            processed_audit_text_builder=lambda msg: "Test processed",
            failed_audit_text="Test failed",
            parse_input=MagicMock(side_effect=ValueError("not well-formed")),
        )

        # Malformed input is a transformation failure (ValueError path), not an "unexpected error"
        self.assertFalse(result)
        transform.assert_not_called()
        mock_sender.send_message.assert_not_called()
        failed_args = mock_event_logger.log_message_failed.call_args[0]
        self.assertIn("Failed to transform TestTransformer message: not well-formed", failed_args[1])
        self.assertEqual(failed_args[2], "Test failed")

    def test_default_hooks_still_reject_non_hl7_payload(self) -> None:
        mock_event_logger = MagicMock()

        result = process_message(
            message=self._build_message("<Root><a>1</a></Root>"),
            sender_client=MagicMock(),
            event_logger=mock_event_logger,
            transform=MagicMock(),
            transformer_display_name="TestTransformer",
            received_audit_text="Test received",
            processed_audit_text_builder=lambda msg: "Test processed",
            failed_audit_text="Test failed",
        )

        # The default (HL7) behaviour is unchanged for transformers that do not override the hooks
        self.assertFalse(result)
        self.assertEqual(mock_event_logger.log_message_failed.call_args[0][2], "Unexpected processing error")


if __name__ == "__main__":
    unittest.main()
