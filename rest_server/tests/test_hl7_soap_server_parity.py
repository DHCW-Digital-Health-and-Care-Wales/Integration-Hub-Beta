"""Characterization tests: rest_server's `generic` pipeline (configured per docs/rest_merge.md §9
as CONTENT_ADAPTER=soap, VALIDATOR_TYPE=hl7-xsd, VALIDATION_SCHEMA=phw,
ALLOWED_SOURCE_IDENTIFIERS=328) against hl7_soap_server's SoapMessageProcessor behaviour.

hl7_soap_server is a separate deployable package (own pyproject.toml/venv) and is intentionally
*not* imported here - the "known good" behaviour below is captured directly from reading
hl7_soap_server/hl7_soap_server/soap_processor.py, and the sample LIMS payloads are the same ones
used by hl7_soap_server/tests/test_soap_processor.py, so both services are exercised with
identical input.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from hl7_validation import convert_er7_to_xml_with_flow_schema

from rest_server.content_adapters.soap_adapter import SoapContentAdapter
from rest_server.errors import ValidationError
from rest_server.message_processor import RestMessageProcessor
from rest_server.validators.hl7_xsd_validator import Hl7XsdValidator

# Same fixture as hl7_soap_server/tests/test_soap_processor.py::VALID_ER7_A05.
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


class RestServerSoapParityTests(unittest.TestCase):
    """rest_server configured to match hl7_soap_server's LIMS->MPI deployment (plan §9)."""

    def setUp(self) -> None:
        self.mock_sender = MagicMock()
        self.mock_event_logger = MagicMock()
        self.mock_metric_sender = MagicMock()
        self.mock_message_store = MagicMock()

        self.processor = RestMessageProcessor(
            content_adapter=SoapContentAdapter(),
            validator=Hl7XsdValidator(schema_group="phw", allowed_structures={"ADT_A05", "ADT_A39"}),
            sender_client=self.mock_sender,
            event_logger=self.mock_event_logger,
            metric_sender=self.mock_metric_sender,
            message_store_client=self.mock_message_store,
            workflow_id="workflow-soap",
            egress_session_id="soap-session",
            allowed_source_identifiers=["328"],
            output_format="er7",
        )

        valid_payload_xml = convert_er7_to_xml_with_flow_schema(VALID_ER7_A05, "phw")
        self.valid_soap_xml = _wrap_payload_in_soap(valid_payload_xml)

    def test_valid_request_matches_hl7_soap_server_200_and_forwards(self) -> None:
        # hl7_soap_server: 200, "<Status>Success</Status>", sends ER7 to Service Bus once.
        status_code, response_xml = self.processor.process(self.valid_soap_xml)

        self.assertEqual(status_code, 200)
        self.assertIn("<Status>Success</Status>", response_xml)
        self.mock_sender.send_text_message.assert_called_once()
        self.mock_message_store.send_to_store.assert_called_once()
        self.assertIn("MSH|^~\\&|328|328", self.mock_sender.send_text_message.call_args.args[0])

    def test_malformed_soap_matches_hl7_soap_server_400_without_schema_validation(self) -> None:
        # hl7_soap_server: 400, "<soapenv:Fault>", validate_xml never reached.
        status_code, response_xml = self.processor.process(INVALID_SOAP_XML)

        self.assertEqual(status_code, 400)
        self.assertIn("<soapenv:Fault>", response_xml)
        self.mock_sender.send_text_message.assert_not_called()

    def test_schema_invalid_payload_matches_hl7_soap_server_400_and_not_forwarded(self) -> None:
        # hl7_soap_server: 400, "Payload schema validation failed" in the fault string.
        invalid_schema_xml = self.valid_soap_xml.replace("<ns0:PID>", "<ns0:PIDX>").replace(
            "</ns0:PID>", "</ns0:PIDX>"
        )

        status_code, response_xml = self.processor.process(invalid_schema_xml)

        self.assertEqual(status_code, 400)
        self.assertIn("Payload schema validation failed", response_xml)
        self.mock_sender.send_text_message.assert_not_called()

    def test_unauthorised_assigning_authority_matches_hl7_soap_server_403(self) -> None:
        # hl7_soap_server: 403, "not authorised" in the fault string.
        invalid_authority_xml = self.valid_soap_xml.replace(
            "<ns0:HD.1>328</ns0:HD.1>", "<ns0:HD.1>999</ns0:HD.1>", 1
        )

        status_code, response_xml = self.processor.process(invalid_authority_xml)

        self.assertEqual(status_code, 403)
        self.assertIn("not authorised", response_xml)
        self.mock_sender.send_text_message.assert_not_called()


class SoapParityKnownGapsTests(unittest.TestCase):
    """Behavioural gaps vs hl7_soap_server found while writing the parity tests above.

    These assert *current* rest_server behaviour (not hl7_soap_server's) so a future fix shows up
    as a failing assertion instead of a silent regression. See docs/rest_merge.md §9.
    """

    def test_missing_assigning_authority_extracts_as_none_not_a_400_fault(self) -> None:
        # GAP: hl7_soap_server's _extract_assigning_authority raises a 400 "Unable to determine
        # assigning authority from payload." immediately when MSH.3/MSH.4/PID.3 carry no HD.1.
        # SoapContentAdapter.extract() instead returns source_identifier=None and defers to the
        # allow-list check in RestMessageProcessor, which rejects None as an *unauthorised*
        # source (403) rather than a *malformed payload* (400) once schema validation passes.
        no_authority_xml = _wrap_payload_in_soap(
            "<ADT_A05><MSH><MSH.10>MSG1</MSH.10></MSH></ADT_A05>"
        )

        extracted = SoapContentAdapter().extract(no_authority_xml)

        self.assertIsNone(extracted.source_identifier)

    def test_unmapped_schema_structure_raises_a_400_not_hl7_soap_servers_500(self) -> None:
        # GAP: hl7_soap_server treats a schema-mapping lookup failure (structure allowed but has
        # no XSD entry for the configured schema group - a deployment misconfiguration) as a 500
        # "Server.Configuration" fault, distinct from a real payload failure. Hl7XsdValidator
        # raises the same ValidationError for both cases, which RestMessageProcessor always maps
        # to 400 "Client.Validation" - masking a server-side config bug as a client error.
        validator = Hl7XsdValidator(schema_group="phw", allowed_structures={"NOT_A_REAL_STRUCTURE"})

        with self.assertRaises(ValidationError):
            validator.validate("<NOT_A_REAL_STRUCTURE/>", "NOT_A_REAL_STRUCTURE")


if __name__ == "__main__":
    unittest.main()
