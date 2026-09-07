"""Integration tests for the FastAPI application endpoints."""
from __future__ import annotations

import unittest

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

    def test_fail_trigger_returns_500(self) -> None:
        response = _client.post(
            "/soap",
            content=_SOAP_FAIL_BODY,
            headers={"Content-Type": "text/xml; charset=utf-8"},
        )
        self.assertEqual(response.status_code, 500)

    def test_fail_trigger_returns_soap_fault(self) -> None:
        response = _client.post(
            "/soap",
            content=_SOAP_FAIL_BODY,
            headers={"Content-Type": "text/xml; charset=utf-8"},
        )
        self.assertIn("Fault", response.text)

    def test_empty_body_does_not_crash(self) -> None:
        response = _client.post(
            "/soap",
            content="",
            headers={"Content-Type": "text/xml"},
        )
        # Empty body is not "fail" — should return an ACK (200) not a server crash (500)
        self.assertNotEqual(response.status_code, 500)


if __name__ == "__main__":
    unittest.main()
