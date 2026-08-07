import unittest
from unittest.mock import MagicMock, patch

from hl7_validation import convert_er7_to_xml_with_flow_schema

from hl7_soap_server.soap_processor import SoapMessageProcessor

VALID_ER7_A05 = "\r".join(
    [
        "MSH|^~\\&|328|328|100|100|2026-07-29 09:50:37||ADT^A28^ADT_A05|6778031837018553261z82215|P|2.5|||||GBR||EN",
        "EVN|A28|20260729095037|20260729095037|||20260729095037",
        "PID|||B0000010612^^^328^PI||LIMS^TEST",
        "PV1||",
    ]
)

INVALID_SOAP_XML = "<not-xml"


def _wrap_payload_in_soap(payload_xml: str) -> str:
    return (
        '<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">'
        "<SOAP-ENV:Body>"
        f"{payload_xml}"
        "</SOAP-ENV:Body>"
        "</SOAP-ENV:Envelope>"
    )


class TestSoapMessageProcessor(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_sender = MagicMock()
        self.mock_event_logger = MagicMock()
        self.mock_metric_sender = MagicMock()
        self.mock_message_store = MagicMock()

        self.processor = SoapMessageProcessor(
            sender_client=self.mock_sender,
            event_logger=self.mock_event_logger,
            metric_sender=self.mock_metric_sender,
            message_store_client=self.mock_message_store,
            workflow_id="workflow-soap",
            egress_session_id="soap-session",
            schema_group="phw",
            allowed_hl7_structures=["ADT_A05", "ADT_A39"],
            allowed_assigning_authorities=["328"],
        )

        valid_payload_xml = convert_er7_to_xml_with_flow_schema(VALID_ER7_A05, "phw")
        self.valid_soap_xml = _wrap_payload_in_soap(valid_payload_xml)

    def test_valid_request_unwraps_validates_and_forwards(self) -> None:
        status_code, response_xml = self.processor.process(self.valid_soap_xml)

        self.assertEqual(status_code, 200)
        self.assertIn("<Status>Success</Status>", response_xml)
        self.mock_sender.send_text_message.assert_called_once()
        self.mock_message_store.send_to_store.assert_called_once()

    @patch("hl7_soap_server.soap_processor.validate_xml")
    def test_invalid_soap_request_returns_fault_without_schema_validation(self, mock_validate_xml: MagicMock) -> None:
        status_code, response_xml = self.processor.process(INVALID_SOAP_XML)

        self.assertEqual(status_code, 400)
        self.assertIn("<soapenv:Fault>", response_xml)
        mock_validate_xml.assert_not_called()
        self.mock_sender.send_text_message.assert_not_called()

    def test_schema_invalid_payload_returns_fault_and_not_forwarded(self) -> None:
        # Break the payload structure after unwrapping by renaming a required segment.
        invalid_schema_xml = self.valid_soap_xml.replace("<ns0:PID>", "<ns0:PIDX>").replace("</ns0:PID>", "</ns0:PIDX>")

        status_code, response_xml = self.processor.process(invalid_schema_xml)

        self.assertEqual(status_code, 400)
        self.assertIn("Payload schema validation failed", response_xml)
        self.mock_sender.send_text_message.assert_not_called()

    def test_assigning_authority_not_328_returns_fault_and_not_forwarded(self) -> None:
        invalid_authority_xml = self.valid_soap_xml.replace(
            "<ns0:HD.1>328</ns0:HD.1>",
            "<ns0:HD.1>999</ns0:HD.1>",
            1,
        )

        status_code, response_xml = self.processor.process(invalid_authority_xml)

        self.assertEqual(status_code, 403)
        self.assertIn("not authorised", response_xml)
        self.mock_sender.send_text_message.assert_not_called()

    def test_unwrapped_valid_payload_forwards_to_downstream(self) -> None:
        status_code, _ = self.processor.process(self.valid_soap_xml)

        self.assertEqual(status_code, 200)
        send_args = self.mock_sender.send_text_message.call_args
        self.assertIsNotNone(send_args)
        self.assertIn("MSH|^~\\&|328|328", send_args.args[0])
