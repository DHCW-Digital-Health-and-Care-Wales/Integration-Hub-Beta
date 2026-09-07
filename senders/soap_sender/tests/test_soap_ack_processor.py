"""Tests for get_ack_result — SOAP response parsing logic."""
from __future__ import annotations

import unittest

from soap_sender.soap_ack_processor import get_ack_result

_SOAP_ACK_AA = """\
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
  <soapenv:Body>
    <AcknowledgementResponse>
      <Status>AA</Status>
      <MessageControlID>MSG001</MessageControlID>
    </AcknowledgementResponse>
  </soapenv:Body>
</soapenv:Envelope>"""

_SOAP_ACK_CA = _SOAP_ACK_AA.replace("<Status>AA</Status>", "<Status>CA</Status>")

_SOAP_ACK_AE = _SOAP_ACK_AA.replace("<Status>AA</Status>", "<Status>AE</Status>")

_SOAP_FAULT = """\
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
  <soapenv:Body>
    <soapenv:Fault>
      <faultcode>soapenv:Client</faultcode>
      <faultstring>Processing failed</faultstring>
    </soapenv:Fault>
  </soapenv:Body>
</soapenv:Envelope>"""

_EMPTY_200 = ""
_NON_XML = "OK"


class TestGetAckResult(unittest.TestCase):

    def test_http_200_with_aa_returns_true(self) -> None:
        self.assertTrue(get_ack_result(200, _SOAP_ACK_AA))

    def test_http_200_with_ca_returns_true(self) -> None:
        self.assertTrue(get_ack_result(200, _SOAP_ACK_CA))

    def test_http_200_with_ae_returns_false(self) -> None:
        self.assertFalse(get_ack_result(200, _SOAP_ACK_AE))

    def test_http_500_with_fault_returns_false(self) -> None:
        self.assertFalse(get_ack_result(500, _SOAP_FAULT))

    def test_http_200_with_fault_body_returns_false(self) -> None:
        # HTTP 200 but body contains Fault — should still be False
        self.assertFalse(get_ack_result(200, _SOAP_FAULT))

    def test_http_400_returns_false(self) -> None:
        self.assertFalse(get_ack_result(400, "Bad Request"))

    def test_http_503_returns_false(self) -> None:
        self.assertFalse(get_ack_result(503, "Service Unavailable"))

    def test_http_200_empty_body_returns_true(self) -> None:
        # No status element and no fault — treat HTTP 200 as success
        self.assertTrue(get_ack_result(200, _EMPTY_200))

    def test_http_200_non_xml_body_returns_true(self) -> None:
        # Non-XML 200 response with no "Fault" text — treat as success
        self.assertTrue(get_ack_result(200, _NON_XML))

    def test_http_202_with_aa_returns_true(self) -> None:
        self.assertTrue(get_ack_result(202, _SOAP_ACK_AA))


if __name__ == "__main__":
    unittest.main()
