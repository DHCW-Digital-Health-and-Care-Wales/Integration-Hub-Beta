"""Tests for the SOAP handler (parse_soap_request) and response builder."""
from __future__ import annotations

import unittest

from http_mock_receiver.soap_handler import parse_soap_request
from http_mock_receiver.soap_response_builder import build_ack_response, build_fault_response

_SOAP_11_ACK = """\
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
  <soapenv:Header/>
  <soapenv:Body>
    <SendHL7Message>
      <hl7Message>MSH|^~\\&amp;|SENDAPP|SENDFAC|RECVAPP|RECVFAC|20250703120000||ADT^A01^ADT_A01|MSG000001|P|2.5
EVN||20250703120000
PID|||1234567890^^^^NH||JONES^GARETH^^^Mr||19800115|M</hl7Message>
    </SendHL7Message>
  </soapenv:Body>
</soapenv:Envelope>"""

_SOAP_12_ENVELOPE = """\
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://www.w3.org/2003/05/soap-envelope">
  <soapenv:Body>
    <SendHL7Message>
      <hl7Message>MSH|^~\\&amp;|APP|FAC|RCV|RCV|20250101||ADT^A28|CTRLID999|P|2.5</hl7Message>
    </SendHL7Message>
  </soapenv:Body>
</soapenv:Envelope>"""

_SOAP_FAIL_BODY = """\
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
  <soapenv:Body>
    <SendHL7Message>
      <hl7Message>MSH|fail|test</hl7Message>
    </SendHL7Message>
  </soapenv:Body>
</soapenv:Envelope>"""

_SOAP_REJECT_BODY = """\
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
  <soapenv:Body>
    <SendHL7Message>
      <hl7Message>MSH|reject|test</hl7Message>
    </SendHL7Message>
  </soapenv:Body>
</soapenv:Envelope>"""

_MALFORMED_XML = "this is not xml at all"

_WIS_ENVELOPE = """\
<?xml version="1.0" encoding="UTF-8"?>
<ns1:Envelope xmlns:ns1="http://Cypris.Nhs.Wales.Uk/CaptureFromFiorona/Input">
  <ns1:Body>
    <ns3:CaptureFromFiorona xmlns:ns3="http://Cypris.Nhs.Wales.Uk/">
      <ns3:inputString>&lt;HL7v2xml&gt;&lt;MSH.1&gt;|&lt;/MSH.1&gt;&lt;/HL7v2xml&gt;</ns3:inputString>
    </ns3:CaptureFromFiorona>
  </ns1:Body>
</ns1:Envelope>"""

_WIS_ENVELOPE_NO_PAYLOAD = """\
<?xml version="1.0" encoding="UTF-8"?>
<ns1:Envelope xmlns:ns1="http://Cypris.Nhs.Wales.Uk/CaptureFromFiorona/Input">
  <ns1:Body>
    <ns3:CaptureFromFiorona xmlns:ns3="http://Cypris.Nhs.Wales.Uk/">
      <ns3:inputString></ns3:inputString>
    </ns3:CaptureFromFiorona>
  </ns1:Body>
</ns1:Envelope>"""


class TestSoapHandler(unittest.TestCase):

    def test_parse_soap11_detects_version(self) -> None:
        result = parse_soap_request(_SOAP_11_ACK)
        self.assertEqual(result.soap_version, "1.1")

    def test_parse_soap12_detects_version(self) -> None:
        result = parse_soap_request(_SOAP_12_ENVELOPE)
        self.assertEqual(result.soap_version, "1.2")

    def test_parse_extracts_hl7_payload(self) -> None:
        result = parse_soap_request(_SOAP_11_ACK)
        assert result.hl7_payload is not None
        self.assertIn("MSH", result.hl7_payload)

    def test_parse_extracts_message_control_id(self) -> None:
        result = parse_soap_request(_SOAP_11_ACK)
        self.assertEqual(result.message_control_id, "MSG000001")

    def test_parse_fail_trigger_sets_fault_flag(self) -> None:
        result = parse_soap_request(_SOAP_FAIL_BODY)
        self.assertTrue(result.is_fault_requested)
        self.assertEqual(result.ack_code, "AE")

    def test_parse_reject_trigger_sets_reject_flag(self) -> None:
        result = parse_soap_request(_SOAP_REJECT_BODY)
        self.assertEqual(result.ack_code, "AR")
        self.assertTrue(result.is_fault_requested)

    def test_parse_normal_message_no_fault_flag(self) -> None:
        result = parse_soap_request(_SOAP_11_ACK)
        self.assertFalse(result.is_fault_requested)
        self.assertEqual(result.ack_code, "AA")

    def test_parse_malformed_xml_returns_result_without_raising(self) -> None:
        # Should not raise — returns a result with is_fault_requested=False
        result = parse_soap_request(_MALFORMED_XML)
        self.assertIsNotNone(result)
        self.assertEqual(result.soap_version, "1.1")

    def test_parse_soap12_extracts_control_id(self) -> None:
        result = parse_soap_request(_SOAP_12_ENVELOPE)
        self.assertEqual(result.message_control_id, "CTRLID999")

    def test_parse_valid_wis_request_extracts_payload(self) -> None:
        result = parse_soap_request(_WIS_ENVELOPE)
        self.assertIsNone(result.hl7_payload)
        self.assertTrue(result.is_well_formed_xml)
        assert result.wis_payload is not None
        self.assertIn("HL7v2xml", result.wis_payload)

    def test_parse_wis_request_no_fault(self) -> None:
        result = parse_soap_request(_WIS_ENVELOPE)
        self.assertFalse(result.is_fault_requested)
        self.assertEqual(result.ack_code, "AA")

    def test_parse_wis_request_no_payload_falls_back_to_raw_envelope(self) -> None:
        result = parse_soap_request(_WIS_ENVELOPE_NO_PAYLOAD)
        self.assertIsNone(result.hl7_payload)
        self.assertIsNone(result.wis_payload)
        self.assertTrue(result.is_well_formed_xml)
        self.assertEqual(result.raw_body, _WIS_ENVELOPE_NO_PAYLOAD)

    def test_parse_malformed_xml_is_not_well_formed(self) -> None:
        result = parse_soap_request(_MALFORMED_XML)
        self.assertFalse(result.is_well_formed_xml)
        self.assertIsNone(result.wis_payload)


class TestSoapResponseBuilder(unittest.TestCase):

    def test_ack_response_contains_aa_status(self) -> None:
        body, _ = build_ack_response("CTRL001")
        self.assertIn("<Status>AA</Status>", body)

    def test_ack_response_contains_control_id(self) -> None:
        body, _ = build_ack_response("CTRL001")
        self.assertIn("<MessageControlID>CTRL001</MessageControlID>", body)

    def test_ack_response_soap11_content_type(self) -> None:
        _, ct = build_ack_response("X", soap_version="1.1")
        self.assertIn("text/xml", ct)

    def test_ack_response_soap12_content_type(self) -> None:
        _, ct = build_ack_response("X", soap_version="1.2")
        self.assertIn("application/soap+xml", ct)

    def test_fault_response_contains_fault_element(self) -> None:
        body, _ = build_fault_response("something went wrong")
        self.assertIn("Fault", body)

    def test_fault_response_soap12_structure(self) -> None:
        body, _ = build_fault_response("err", soap_version="1.2")
        self.assertIn("soapenv:Code", body)

    def test_ack_escapes_special_characters(self) -> None:
        body, _ = build_ack_response("ID&<>\"")
        self.assertIn("&amp;", body)
        self.assertIn("&lt;", body)
        self.assertIn("&gt;", body)


if __name__ == "__main__":
    unittest.main()
