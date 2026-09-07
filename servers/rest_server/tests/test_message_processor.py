import unittest
from unittest.mock import MagicMock, patch

from rest_server.errors import RequestError, ValidationError
from rest_server.message_processor import RestMessageProcessor


class TestRestMessageProcessor(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_adapter = MagicMock()
        self.mock_adapter.content_type = "application/xml; charset=utf-8"
        self.mock_validator = MagicMock()
        self.mock_sender = MagicMock()
        self.mock_event_logger = MagicMock()
        self.mock_metric_sender = MagicMock()
        self.mock_message_store = MagicMock()

        self.processor = RestMessageProcessor(
            content_adapter=self.mock_adapter,
            validator=self.mock_validator,
            sender_client=self.mock_sender,
            event_logger=self.mock_event_logger,
            metric_sender=self.mock_metric_sender,
            message_store_client=self.mock_message_store,
            workflow_id="workflow-rest",
            egress_session_id="rest-session",
            allowed_source_identifiers=["partner-x"],
            output_format="raw",
        )

    def _extracted(self, **overrides: object) -> MagicMock:
        extracted = MagicMock()
        extracted.payload_xml = "<Document><Body>content</Body></Document>"
        extracted.structure_id = "Document"
        extracted.source_identifier = "partner-x"
        extracted.message_control_id = "msg-1"
        for key, value in overrides.items():
            setattr(extracted, key, value)
        return extracted

    def test_valid_request_validates_and_forwards(self) -> None:
        self.mock_adapter.extract.return_value = self._extracted()
        self.mock_adapter.build_success_response.return_value = "<ack/>"

        status_code, body = self.processor.process("<Document/>")

        self.assertEqual(status_code, 200)
        self.assertEqual(body, "<ack/>")
        self.mock_validator.validate.assert_called_once()
        self.mock_sender.send_text_message.assert_called_once()
        self.mock_message_store.send_to_store.assert_called_once()

    def test_disallowed_source_identifier_returns_403_and_does_not_forward(self) -> None:
        self.mock_adapter.extract.return_value = self._extracted(source_identifier="unknown-source")
        self.mock_adapter.build_error_response.return_value = "<error/>"

        status_code, _ = self.processor.process("<Document/>")

        self.assertEqual(status_code, 403)
        self.mock_sender.send_text_message.assert_not_called()

    def test_adapter_request_error_returns_its_http_status(self) -> None:
        self.mock_adapter.extract.side_effect = RequestError("Client", "malformed", 400)
        self.mock_adapter.build_error_response.return_value = "<error/>"

        status_code, _ = self.processor.process("<not-xml")

        self.assertEqual(status_code, 400)
        self.mock_validator.validate.assert_not_called()
        self.mock_sender.send_text_message.assert_not_called()

    def test_validation_error_returns_400_and_does_not_forward(self) -> None:
        self.mock_adapter.extract.return_value = self._extracted()
        self.mock_validator.validate.side_effect = ValidationError("schema invalid")
        self.mock_adapter.build_error_response.return_value = "<error/>"

        status_code, _ = self.processor.process("<Document/>")

        self.assertEqual(status_code, 400)
        self.mock_sender.send_text_message.assert_not_called()

    @patch("rest_server.message_processor.xml_to_er7")
    def test_er7_output_format_converts_payload_before_sending(self, mock_xml_to_er7: MagicMock) -> None:
        mock_xml_to_er7.return_value = "MSH|^~\\&|..."
        self.processor.output_format = "er7"
        self.mock_adapter.extract.return_value = self._extracted()
        self.mock_adapter.build_success_response.return_value = "<ack/>"

        self.processor.process("<Document/>")

        mock_xml_to_er7.assert_called_once()
        send_args = self.mock_sender.send_text_message.call_args
        self.assertEqual(send_args.args[0], "MSH|^~\\&|...")

    def test_unexpected_exception_returns_500(self) -> None:
        self.mock_adapter.extract.side_effect = RuntimeError("boom")
        self.mock_adapter.build_error_response.return_value = "<error/>"

        status_code, _ = self.processor.process("<Document/>")

        self.assertEqual(status_code, 500)
        self.mock_sender.send_text_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()
