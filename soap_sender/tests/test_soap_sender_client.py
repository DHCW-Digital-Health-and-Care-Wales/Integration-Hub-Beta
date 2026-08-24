"""Tests for SOAPSenderClient — envelope building and HTTP error mapping."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import requests as req
from defusedxml import ElementTree as ET

from soap_sender.soap_sender_client import SOAPSenderClient, _build_soap_envelope


class TestBuildSoapEnvelope(unittest.TestCase):

    def test_envelope_contains_hl7_payload(self) -> None:
        er7 = "MSH|^~\\&|APP|FAC|RCV|RCV|20250101||ADT^A28|CTRL001|P|2.5"
        env = _build_soap_envelope(er7)
        self.assertIn("MSH", env)

    def test_envelope_wraps_in_send_hl7_message(self) -> None:
        env = _build_soap_envelope("MSH|test")
        self.assertIn("<SendHL7Message>", env)
        self.assertIn("<hl7Message>", env)

    def test_envelope_uses_soap11_namespace(self) -> None:
        env = _build_soap_envelope("MSH|test")
        self.assertIn("http://schemas.xmlsoap.org/soap/envelope/", env)

    def test_envelope_escapes_ampersand(self) -> None:
        env = _build_soap_envelope("MSH|^~\\&|APP")
        self.assertIn("&amp;", env)

    def test_envelope_escapes_lt_gt(self) -> None:
        env = _build_soap_envelope("<tag>")
        self.assertIn("&lt;", env)
        self.assertIn("&gt;", env)

    def test_envelope_is_valid_xml_structure(self) -> None:
        env = _build_soap_envelope("MSH|^~\\&|APP|FAC|RCV|RCV|20250101||ADT^A28|CTRL|P|2.5")
        # Should not raise
        ET.fromstring(env)


class TestSOAPSenderClientSendMessage(unittest.TestCase):

    def _make_client(self) -> SOAPSenderClient:
        return SOAPSenderClient("http://localhost:8080/soap", timeout_seconds=5)

    def test_send_message_returns_status_and_body(self) -> None:
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<ACK/>"
        with patch.object(client._session, "post", return_value=mock_response):
            status, body = client.send_message("MSH|test")
        self.assertEqual(status, 200)
        self.assertEqual(body, "<ACK/>")

    def test_send_message_raises_timeout_error(self) -> None:
        client = self._make_client()
        with patch.object(client._session, "post", side_effect=req.exceptions.Timeout):
            with self.assertRaises(TimeoutError):
                client.send_message("MSH|test", _retry_attempted=True)

    def test_send_message_raises_connection_error(self) -> None:
        client = self._make_client()
        with patch.object(client._session, "post", side_effect=req.exceptions.ConnectionError("refused")):
            with self.assertRaises(ConnectionError):
                client.send_message("MSH|test")

    def test_api_key_added_to_headers(self) -> None:
        client = SOAPSenderClient("http://localhost/soap", api_key="secret123")
        self.assertIn("Authorization", client._session.headers)
        self.assertIn("secret123", client._session.headers["Authorization"])

    def test_no_api_key_no_auth_header(self) -> None:
        client = SOAPSenderClient("http://localhost/soap")
        self.assertNotIn("Authorization", client._session.headers)

    def test_context_manager_closes_session(self) -> None:
        with SOAPSenderClient("http://localhost/soap") as client:
            self.assertIsNotNone(client._session)
        # After exit, session should be closed (no error raised)


if __name__ == "__main__":
    unittest.main()
