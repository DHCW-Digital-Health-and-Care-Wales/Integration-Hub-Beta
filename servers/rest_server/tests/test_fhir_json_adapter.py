"""Tests for the FHIR JSON content adapter (spike INTHUB-590477)."""
import json
import unittest

from rest_server.content_adapters.fhir_json_adapter import FhirJsonContentAdapter
from rest_server.errors import RequestError

VALID_BUNDLE = json.dumps(
    {
        "resourceType": "Bundle",
        "id": "example-bundle-1",
        "type": "message",
        "meta": {"source": "urn:dhcw:cdr"},
        "entry": [],
    }
)


class TestFhirJsonContentAdapter(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = FhirJsonContentAdapter()

    def test_extract_valid_bundle(self) -> None:
        extracted = self.adapter.extract(VALID_BUNDLE)

        self.assertEqual(extracted.structure_id, "Bundle")
        self.assertEqual(extracted.source_identifier, "urn:dhcw:cdr")
        self.assertEqual(extracted.message_control_id, "example-bundle-1")
        self.assertEqual(extracted.payload_xml, VALID_BUNDLE)

    def test_malformed_json_raises_request_error(self) -> None:
        with self.assertRaises(RequestError) as ctx:
            self.adapter.extract("{not-json")
        self.assertEqual(ctx.exception.http_status, 400)

    def test_non_object_json_raises_request_error(self) -> None:
        with self.assertRaises(RequestError) as ctx:
            self.adapter.extract("[1, 2, 3]")
        self.assertEqual(ctx.exception.http_status, 400)

    def test_missing_resource_type_raises_request_error(self) -> None:
        with self.assertRaises(RequestError) as ctx:
            self.adapter.extract(json.dumps({"id": "no-type"}))
        self.assertEqual(ctx.exception.http_status, 400)

    def test_build_success_response_is_operation_outcome(self) -> None:
        response = json.loads(self.adapter.build_success_response("example-bundle-1"))

        self.assertEqual(response["resourceType"], "OperationOutcome")
        self.assertEqual(response["issue"][0]["severity"], "information")

    def test_build_error_response_is_operation_outcome(self) -> None:
        response = json.loads(self.adapter.build_error_response("Client.Validation", "boom"))

        self.assertEqual(response["resourceType"], "OperationOutcome")
        self.assertEqual(response["issue"][0]["severity"], "error")
        self.assertEqual(response["issue"][0]["diagnostics"], "boom")


if __name__ == "__main__":
    unittest.main()
