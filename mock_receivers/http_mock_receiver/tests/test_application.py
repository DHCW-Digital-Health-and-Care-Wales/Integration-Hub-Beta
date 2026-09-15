"""Integration tests for the FastAPI application endpoints."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from http_mock_receiver.application import app

_client = TestClient(app, raise_server_exceptions=False)

_SOAP_11_BODY = """\
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
  <soapenv:Header/>
  <soapenv:Body>
    <SendHL7Message>
      <hl7Message>MSH|^~\\&amp;|APP|FAC|RCV|RCV|20250101||ADT^A28|MSG001|P|2.5
EVN||20250101
PID|||9999999^^^^NH||TEST^PATIENT</hl7Message>
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

_MALFORMED_XML = "this is not xml at all"


class TestHealthEndpoint(unittest.TestCase):

    def test_health_returns_200(self) -> None:
        response = _client.get("/health")
        self.assertEqual(response.status_code, 200)

    def test_health_returns_ok(self) -> None:
        response = _client.get("/health")
        self.assertEqual(response.text, "OK")


class TestSoapEndpoint(unittest.TestCase):

    def test_valid_soap_returns_200(self) -> None:
        response = _client.post(
            "/soap",
            content=_SOAP_11_BODY,
            headers={"Content-Type": "text/xml; charset=utf-8"},
        )
        self.assertEqual(response.status_code, 200)

    def test_valid_soap_returns_xml(self) -> None:
        response = _client.post(
            "/soap",
            content=_SOAP_11_BODY,
            headers={"Content-Type": "text/xml; charset=utf-8"},
        )
        self.assertIn("text/xml", response.headers["content-type"])

    def test_valid_soap_response_contains_aa(self) -> None:
        response = _client.post(
            "/soap",
            content=_SOAP_11_BODY,
            headers={"Content-Type": "text/xml; charset=utf-8"},
        )
        self.assertIn("AA", response.text)

    def test_fail_trigger_returns_500_and_ae_status(self) -> None:
        response = _client.post(
            "/soap",
            content=_SOAP_FAIL_BODY,
            headers={"Content-Type": "text/xml; charset=utf-8"},
        )
        self.assertEqual(response.status_code, 500)
        self.assertIn("<Status>AE</Status>", response.text)

    def test_reject_trigger_returns_500_and_ar_status(self) -> None:
        response = _client.post(
            "/soap",
            content=_SOAP_REJECT_BODY,
            headers={"Content-Type": "text/xml; charset=utf-8"},
        )
        self.assertEqual(response.status_code, 500)
        self.assertIn("<Status>AR</Status>", response.text)

    def test_empty_body_does_not_crash(self) -> None:
        response = _client.post(
            "/soap",
            content="",
            headers={"Content-Type": "text/xml"},
        )
        # Empty body is not "fail" — should return an ACK (200) not a server crash (500)
        self.assertNotEqual(response.status_code, 500)


class TestServiceBusForwarding(unittest.TestCase):
    """Verifies Service Bus forwarding decisions for HL7 and WIS SOAP requests."""

    def test_hl7_soap_forwards_hl7_payload(self) -> None:
        fake_sender = MagicMock()
        with patch("http_mock_receiver.application._sb_sender", fake_sender):
            _client.post(
                "/soap",
                content=_SOAP_11_BODY,
                headers={"Content-Type": "text/xml; charset=utf-8"},
            )
        fake_sender.send_text_message.assert_called_once()
        forwarded = fake_sender.send_text_message.call_args[0][0]
        self.assertIn("MSH", forwarded)

    def test_valid_wis_request_forwards_extracted_payload(self) -> None:
        fake_sender = MagicMock()
        with patch("http_mock_receiver.application._sb_sender", fake_sender):
            response = _client.post(
                "/soap",
                content=_WIS_ENVELOPE,
                headers={"Content-Type": "text/xml; charset=utf-8"},
            )
        self.assertEqual(response.status_code, 200)
        fake_sender.send_text_message.assert_called_once()
        forwarded = fake_sender.send_text_message.call_args[0][0]
        self.assertIn("HL7v2xml", forwarded)

    def test_wis_request_with_no_payload_forwards_raw_envelope(self) -> None:
        fake_sender = MagicMock()
        with patch("http_mock_receiver.application._sb_sender", fake_sender):
            response = _client.post(
                "/soap",
                content=_WIS_ENVELOPE_NO_PAYLOAD,
                headers={"Content-Type": "text/xml; charset=utf-8"},
            )
        self.assertEqual(response.status_code, 200)
        fake_sender.send_text_message.assert_called_once_with(_WIS_ENVELOPE_NO_PAYLOAD)

    def test_malformed_xml_does_not_forward(self) -> None:
        fake_sender = MagicMock()
        with patch("http_mock_receiver.application._sb_sender", fake_sender):
            _client.post(
                "/soap",
                content=_MALFORMED_XML,
                headers={"Content-Type": "text/xml; charset=utf-8"},
            )
        fake_sender.send_text_message.assert_not_called()

    def test_fail_trigger_does_not_forward(self) -> None:
        fake_sender = MagicMock()
        with patch("http_mock_receiver.application._sb_sender", fake_sender):
            _client.post(
                "/soap",
                content=_SOAP_FAIL_BODY,
                headers={"Content-Type": "text/xml; charset=utf-8"},
            )
        fake_sender.send_text_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()
