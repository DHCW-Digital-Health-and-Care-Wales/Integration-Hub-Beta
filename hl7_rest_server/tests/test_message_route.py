"""End-to-end tests for the POST /hl7MessageReceiver route via the FastAPI TestClient."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from hl7_rest_server.app import create_app
from tests.helpers import VALID_ER7_MESSAGE, build_test_context, make_config


class MessageRouteTests(unittest.TestCase):
    def _client(self, **kwargs: object) -> tuple[TestClient, MagicMock, MagicMock]:
        context, sender, store = build_test_context(**kwargs)  # type: ignore[arg-type]
        return TestClient(create_app(context)), sender, store

    def test_valid_er7_returns_201_with_raw_ack_and_sends_once(self) -> None:
        client, sender, _ = self._client()
        response = client.post("/hl7MessageReceiver", json={"messageContent": VALID_ER7_MESSAGE})
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.text.startswith("MSH|^~\\&|DHCW|cymru.nhs.uk|"))
        self.assertIn("MSA|AA|MSGID12345", response.text)
        sender.send_text_message.assert_called_once()

    def test_valid_xml_is_converted_and_returns_201(self) -> None:
        client, sender, _ = self._client()
        xml_message = _er7_to_min_xml()
        response = client.post("/hl7MessageReceiver", json={"messageContent": xml_message})
        self.assertEqual(response.status_code, 201)
        self.assertIn("MSA|AA|MSGID12345", response.text)
        sender.send_text_message.assert_called_once()

    def test_validation_failure_returns_422_envelope_without_send(self) -> None:
        # Configure a version constraint the message violates → validation NACK.
        client, sender, _ = self._client(hl7_version="2.9")
        response = client.post("/hl7MessageReceiver", json={"messageContent": VALID_ER7_MESSAGE})
        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body["StatusCode"], 422)
        self.assertIn("MSA|AR|MSGID12345", body["ErrorMessage"])
        sender.send_text_message.assert_not_called()

    def test_unparsable_message_returns_500_generic_nack(self) -> None:
        client, sender, _ = self._client()
        response = client.post("/hl7MessageReceiver", json={"messageContent": "this is not an HL7 message"})
        self.assertEqual(response.status_code, 500)
        body = response.json()
        self.assertEqual(body["StatusCode"], 500)
        self.assertIn("MSA|AE|", body["ErrorMessage"])
        # Generated control id must be <= 20 characters.
        control_id = body["ErrorMessage"].split("MSA|AE|")[1].split("|")[0]
        self.assertLessEqual(len(control_id), 20)
        sender.send_text_message.assert_not_called()

    def test_oversize_message_returns_400(self) -> None:
        client, sender, _ = self._client(config=make_config(max_message_size_bytes=10))
        response = client.post("/hl7MessageReceiver", json={"messageContent": VALID_ER7_MESSAGE})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["StatusCode"], 400)
        sender.send_text_message.assert_not_called()

    def test_missing_body_field_returns_400(self) -> None:
        client, _, _ = self._client()
        response = client.post("/hl7MessageReceiver", json={"wrong": "field"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["StatusCode"], 400)

    def test_unknown_route_returns_404(self) -> None:
        client, _, _ = self._client()
        self.assertEqual(client.get("/does-not-exist").status_code, 404)

    def test_service_bus_send_failure_returns_500_no_ack(self) -> None:
        client, sender, _ = self._client()
        sender.send_text_message.side_effect = RuntimeError("Service Bus unavailable")
        response = client.post("/hl7MessageReceiver", json={"messageContent": VALID_ER7_MESSAGE})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["StatusCode"], 500)


def _er7_to_min_xml() -> str:
    """A minimal HL7 v2 XML document equivalent to the test ER7 message."""
    return (
        '<ADT_A05 xmlns="urn:hl7-org:v2xml">'
        "<MSH>"
        "<MSH.1>|</MSH.1>"
        "<MSH.2>^~\\&amp;</MSH.2>"
        "<MSH.3><HD.1>252</HD.1></MSH.3>"
        "<MSH.4><HD.1>252</HD.1></MSH.4>"
        "<MSH.5><HD.1>MPI</HD.1></MSH.5>"
        "<MSH.6><HD.1>MPI</HD.1></MSH.6>"
        "<MSH.7><TS.1>20240101120000</TS.1></MSH.7>"
        "<MSH.9><MSG.1>ADT</MSG.1><MSG.2>A28</MSG.2><MSG.3>ADT_A05</MSG.3></MSH.9>"
        "<MSH.10>MSGID12345</MSH.10>"
        "<MSH.11><PT.1>P</PT.1></MSH.11>"
        "<MSH.12><VID.1>2.5</VID.1></MSH.12>"
        "</MSH>"
        "<EVN><EVN.1>A28</EVN.1><EVN.2><TS.1>20240101120000</TS.1></EVN.2></EVN>"
        "<PID><PID.1>1</PID.1><PID.3><CX.1>123456</CX.1></PID.3>"
        "<PID.5><XPN.1><FN.1>SMITH</FN.1></XPN.1><XPN.2>JOHN</XPN.2></PID.5></PID>"
        "</ADT_A05>"
    )


if __name__ == "__main__":
    unittest.main()
