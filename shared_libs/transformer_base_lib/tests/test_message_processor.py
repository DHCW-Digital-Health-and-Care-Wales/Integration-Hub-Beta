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
            "EventId": "123e4567-e89b-12d3-a456-426614174000",
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


if __name__ == "__main__":
    unittest.main()
