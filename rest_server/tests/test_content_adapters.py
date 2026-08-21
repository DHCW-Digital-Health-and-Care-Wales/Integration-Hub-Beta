import unittest

from rest_server.content_adapters.soap_adapter import SoapContentAdapter
from rest_server.content_adapters.xml_raw_adapter import XmlRawContentAdapter
from rest_server.errors import RequestError

VALID_PAYLOAD_XML = (
    '<ns0:ADT_A05 xmlns:ns0="urn:hl7-org:v2xml">'
    "<ns0:MSH>"
    "<ns0:MSH.3><ns0:HD.1>328</ns0:HD.1></ns0:MSH.3>"
    "<ns0:MSH.10>6774333028472727804z213950</ns0:MSH.10>"
    "</ns0:MSH>"
    "</ns0:ADT_A05>"
)


def _wrap_in_soap(payload_xml: str) -> str:
    return (
        '<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">'
        f"<SOAP-ENV:Body>{payload_xml}</SOAP-ENV:Body>"
        "</SOAP-ENV:Envelope>"
    )


class TestSoapContentAdapter(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = SoapContentAdapter()

    def test_extract_valid_soap_request(self) -> None:
        extracted = self.adapter.extract(_wrap_in_soap(VALID_PAYLOAD_XML))

        self.assertEqual(extracted.structure_id, "ADT_A05")
        self.assertEqual(extracted.source_identifier, "328")
        self.assertEqual(extracted.message_control_id, "6774333028472727804z213950")
        self.assertIn("<ns0:ADT_A05", extracted.payload_xml)

    def test_malformed_xml_raises_request_error(self) -> None:
        with self.assertRaises(RequestError) as ctx:
            self.adapter.extract("<not-xml")
        self.assertEqual(ctx.exception.http_status, 400)

    def test_missing_body_raises_request_error(self) -> None:
        envelope_without_body = (
            '<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"/>'
        )
        with self.assertRaises(RequestError) as ctx:
            self.adapter.extract(envelope_without_body)
        self.assertEqual(ctx.exception.http_status, 400)

    def test_multiple_body_children_raises_request_error(self) -> None:
        two_children = _wrap_in_soap(VALID_PAYLOAD_XML + VALID_PAYLOAD_XML)
        with self.assertRaises(RequestError) as ctx:
            self.adapter.extract(two_children)
        self.assertEqual(ctx.exception.http_status, 400)

    def test_build_success_response_contains_message_control_id(self) -> None:
        response = self.adapter.build_success_response("abc123")
        self.assertIn("<Status>Success</Status>", response)
        self.assertIn("<MessageControlId>abc123</MessageControlId>", response)

    def test_build_error_response_contains_fault(self) -> None:
        response = self.adapter.build_error_response("Client", "bad request")
        self.assertIn("<soapenv:Fault>", response)
        self.assertIn("bad request", response)


class TestXmlRawContentAdapter(unittest.TestCase):
    def test_extract_with_locators(self) -> None:
        adapter = XmlRawContentAdapter(
            source_identifier_path=["Header", "SourceSystem"],
            message_control_id_path=["Header", "MessageId"],
        )
        raw_xml = (
            "<Document>"
            "<Header><SourceSystem>partner-x</SourceSystem><MessageId>msg-1</MessageId></Header>"
            "<Body>content</Body>"
            "</Document>"
        )

        extracted = adapter.extract(raw_xml)

        self.assertEqual(extracted.structure_id, "Document")
        self.assertEqual(extracted.source_identifier, "partner-x")
        self.assertEqual(extracted.message_control_id, "msg-1")
        self.assertEqual(extracted.payload_xml, raw_xml)

    def test_extract_without_locators_returns_none_metadata(self) -> None:
        adapter = XmlRawContentAdapter()

        extracted = adapter.extract("<Document><Body>content</Body></Document>")

        self.assertIsNone(extracted.source_identifier)
        self.assertIsNone(extracted.message_control_id)

    def test_malformed_xml_raises_request_error(self) -> None:
        adapter = XmlRawContentAdapter()
        with self.assertRaises(RequestError) as ctx:
            adapter.extract("<not-xml")
        self.assertEqual(ctx.exception.http_status, 400)

    def test_build_success_and_error_responses(self) -> None:
        adapter = XmlRawContentAdapter()
        success = adapter.build_success_response("msg-1")
        error = adapter.build_error_response("Client.Validation", "invalid")

        self.assertIn("<status>Success</status>", success)
        self.assertIn("<messageControlId>msg-1</messageControlId>", success)
        self.assertIn("<code>Client.Validation</code>", error)
        self.assertIn("<message>invalid</message>", error)


if __name__ == "__main__":
    unittest.main()
