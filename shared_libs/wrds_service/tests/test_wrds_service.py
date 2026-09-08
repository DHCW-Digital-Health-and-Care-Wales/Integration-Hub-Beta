"""Tests for WRDSService — envelope building, response parsing, and get_to_code filtering."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

import requests as req

from wrds_service.wrds_service import (
    WRDSService,
    WRDSServiceError,
    _build_get_result_set_envelope,
    _parse_get_result_set_response,
    _xml_escape,
)

_NRDS_NS = "http://www.wales.nhs.uk/nrds"
_MES_NS = "http://www.wales.nhs.uk/namespaces/MessageRelease2"


def _fake_response(status_code: int, text: str) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    return response


def _multi_row_response_xml() -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <GetResultSetResponse xmlns="{_MES_NS}">
      <Row>
        <AttributeValuePair>
          <Attribute><Id>1</Id><Name>FromCode</Name><Namespace>{_NRDS_NS}</Namespace></Attribute>
          <Value>11</Value>
        </AttributeValuePair>
        <AttributeValuePair>
          <Attribute><Id>2</Id><Name>ToCode</Name><Namespace>{_NRDS_NS}</Namespace></Attribute>
          <Value>S</Value>
        </AttributeValuePair>
        <AttributeValuePair>
          <Attribute><Id>3</Id><Name>Type</Name><Namespace>{_NRDS_NS}</Namespace></Attribute>
          <Value>Marital Status</Value>
        </AttributeValuePair>
      </Row>
      <Row>
        <AttributeValuePair>
          <Attribute><Id>4</Id><Name>FromCode</Name><Namespace>{_NRDS_NS}</Namespace></Attribute>
          <Value>ZZ</Value>
        </AttributeValuePair>
        <AttributeValuePair>
          <Attribute><Id>5</Id><Name>ToCode</Name><Namespace>{_NRDS_NS}</Namespace></Attribute>
          <Value></Value>
        </AttributeValuePair>
        <AttributeValuePair>
          <Attribute><Id>6</Id><Name>Type</Name><Namespace>{_NRDS_NS}</Namespace></Attribute>
          <Value>Ethnicity</Value>
        </AttributeValuePair>
      </Row>
    </GetResultSetResponse>
  </soap:Body>
</soap:Envelope>"""


def _fault_response_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <soap:Fault>
      <faultcode>soap:Server</faultcode>
      <faultstring>Internal error</faultstring>
    </soap:Fault>
  </soap:Body>
</soap:Envelope>"""


class TestBuildGetResultSetEnvelope(unittest.TestCase):
    def test_includes_one_attribute_value_pair_per_attribute(self) -> None:
        envelope = _build_get_result_set_envelope(
            "FioranoCodeTranslation",
            [("FromSystem", "349"), ("ToSystem", "100")],
            ["FromCode", "type", "ToCode"],
            exact_match=True,
        )

        self.assertEqual(envelope.count("<AttributeValuePair>"), 2)
        self.assertIn("<Name>FromSystem</Name>", envelope)
        self.assertIn("<Value>349</Value>", envelope)

    def test_includes_one_attribute_to_retrieve_per_entry(self) -> None:
        envelope = _build_get_result_set_envelope(
            "FioranoCodeTranslation", [], ["FromCode", "type", "ToCode"], exact_match=True
        )

        self.assertEqual(envelope.count("<AttributeToRetrieve>"), 3)

    def test_exact_match_true_maps_to_1(self) -> None:
        envelope = _build_get_result_set_envelope("Table", [], [], exact_match=True)

        self.assertIn("<ExactMatch>1</ExactMatch>", envelope)

    def test_exact_match_false_maps_to_0(self) -> None:
        envelope = _build_get_result_set_envelope("Table", [], [], exact_match=False)

        self.assertIn("<ExactMatch>0</ExactMatch>", envelope)

    def test_lookup_table_name_included(self) -> None:
        envelope = _build_get_result_set_envelope("FioranoCodeTranslation", [], [], exact_match=True)

        self.assertIn("<Name>FioranoCodeTranslation</Name>", envelope)

    def test_escapes_special_characters_in_attribute_values(self) -> None:
        envelope = _build_get_result_set_envelope(
            "Table", [("FromSystem", "A & B <test>")], [], exact_match=True
        )

        self.assertIn("A &amp; B &lt;test&gt;", envelope)
        self.assertNotIn("A & B <test>", envelope)


class TestXmlEscape(unittest.TestCase):
    def test_escapes_ampersand_lt_gt(self) -> None:
        self.assertEqual(_xml_escape("A & B < C > D"), "A &amp; B &lt; C &gt; D")


class TestParseGetResultSetResponse(unittest.TestCase):
    def test_parses_multiple_rows(self) -> None:
        rows = _parse_get_result_set_response(_multi_row_response_xml())

        self.assertEqual(len(rows), 2)

    def test_row_values_keyed_by_attribute_name(self) -> None:
        rows = _parse_get_result_set_response(_multi_row_response_xml())

        self.assertEqual(rows[0]["FromCode"], "11")
        self.assertEqual(rows[0]["ToCode"], "S")
        self.assertEqual(rows[0]["Type"], "Marital Status")

    def test_empty_value_preserved_as_empty_string(self) -> None:
        rows = _parse_get_result_set_response(_multi_row_response_xml())

        self.assertEqual(rows[1]["ToCode"], "")

    def test_soap_fault_raises_wrds_service_error(self) -> None:
        with self.assertRaises(WRDSServiceError):
            _parse_get_result_set_response(_fault_response_xml())

    def test_invalid_xml_raises_wrds_service_error(self) -> None:
        with self.assertRaises(WRDSServiceError):
            _parse_get_result_set_response("not xml")

    def test_missing_body_raises_wrds_service_error(self) -> None:
        with self.assertRaises(WRDSServiceError):
            _parse_get_result_set_response("<root></root>")


class TestWRDSServiceGetResultSet(unittest.TestCase):
    def test_returns_parsed_rows_on_success(self) -> None:
        service = WRDSService(endpoint_url="https://example.test/wrdssoapservice")
        service._session = MagicMock()
        service._session.post.return_value = _fake_response(200, _multi_row_response_xml())

        rows = service.get_result_set(
            lookup_table_name="FioranoCodeTranslation",
            attributes=[("FromSystem", "349"), ("ToSystem", "100")],
            attributes_to_retrieve=["FromCode", "type", "ToCode"],
        )

        self.assertEqual(len(rows), 2)
        service._session.post.assert_called_once()

    def test_non_200_status_raises_wrds_service_error(self) -> None:
        service = WRDSService(endpoint_url="https://example.test/wrdssoapservice")
        service._session = MagicMock()
        service._session.post.return_value = _fake_response(500, "")

        with self.assertRaises(WRDSServiceError):
            service.get_result_set("Table", [], [])

    def test_timeout_raises_wrds_service_error(self) -> None:
        service = WRDSService(endpoint_url="https://example.test/wrdssoapservice")
        service._session = MagicMock()
        service._session.post.side_effect = req.exceptions.Timeout()

        with self.assertRaises(WRDSServiceError):
            service.get_result_set("Table", [], [])

    def test_connection_error_raises_wrds_service_error(self) -> None:
        service = WRDSService(endpoint_url="https://example.test/wrdssoapservice")
        service._session = MagicMock()
        service._session.post.side_effect = req.exceptions.ConnectionError()

        with self.assertRaises(WRDSServiceError):
            service.get_result_set("Table", [], [])

    def test_client_cert_path_passed_to_post(self) -> None:
        service = WRDSService(
            endpoint_url="https://example.test/wrdssoapservice", client_cert_path="certs/client.pem"
        )
        service._session = MagicMock()
        service._session.post.return_value = _fake_response(200, _multi_row_response_xml())

        service.get_result_set("Table", [], [])

        _, kwargs = service._session.post.call_args
        self.assertEqual(kwargs["cert"], "certs/client.pem")


class TestWRDSServiceGetToCode(unittest.TestCase):
    def setUp(self) -> None:
        self.service = WRDSService(endpoint_url="https://example.test/wrdssoapservice")
        self.rows = _parse_get_result_set_response(_multi_row_response_xml())

    def test_matches_on_from_code_and_type(self) -> None:
        # Response attribute name is "Type" (capitalised) — get_to_code() must still match it
        # against the confirmed reference_type value "Marital Status" case-insensitively on names.
        to_code = self.service.get_to_code(self.rows, from_code="11", reference_type="Marital Status")

        self.assertEqual(to_code, "S")

    def test_returns_empty_string_when_matching_row_has_empty_to_code(self) -> None:
        to_code = self.service.get_to_code(self.rows, from_code="ZZ", reference_type="Ethnicity")

        self.assertEqual(to_code, "")

    def test_returns_empty_string_when_no_matching_row(self) -> None:
        to_code = self.service.get_to_code(self.rows, from_code="99", reference_type="Sex")

        self.assertEqual(to_code, "")


class TestWRDSServiceContextManager(unittest.TestCase):
    def test_context_manager_closes_session(self) -> None:
        with WRDSService(endpoint_url="https://example.test/wrdssoapservice") as service:
            service._session = MagicMock()
            session_mock = service._session

        session_mock.close.assert_called_once()


class TestWRDSServiceLocalFixture(unittest.TestCase):
    def test_returns_rows_from_fixture_file_without_network_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            fixture_path = Path(tmp_dir) / "wrds_local_fixture.xml"
            fixture_path.write_text(_multi_row_response_xml(), encoding="utf-8")

            service = WRDSService(
                endpoint_url="https://example.test/wrdssoapservice",
                fixture_file_path=str(fixture_path),
            )
            service._session = MagicMock()

            rows = service.get_result_set("FioranoCodeTranslation", [("FromSystem", "349")], ["FromCode"])

        self.assertEqual(rows, _parse_get_result_set_response(_multi_row_response_xml()))
        service._session.post.assert_not_called()

    def test_missing_fixture_file_raises_wrds_service_error(self) -> None:
        service = WRDSService(
            endpoint_url="https://example.test/wrdssoapservice",
            fixture_file_path="/no/such/file.xml",
        )

        with self.assertRaises(WRDSServiceError):
            service.get_result_set("Table", [], [])

    def test_invalid_xml_fixture_raises_wrds_service_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            fixture_path = Path(tmp_dir) / "wrds_local_fixture.xml"
            fixture_path.write_text("not xml", encoding="utf-8")

            service = WRDSService(
                endpoint_url="https://example.test/wrdssoapservice",
                fixture_file_path=str(fixture_path),
            )

            with self.assertRaises(WRDSServiceError):
                service.get_result_set("Table", [], [])

    def test_soap_fault_fixture_raises_wrds_service_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            fixture_path = Path(tmp_dir) / "wrds_local_fixture.xml"
            fixture_path.write_text(_fault_response_xml(), encoding="utf-8")

            service = WRDSService(
                endpoint_url="https://example.test/wrdssoapservice",
                fixture_file_path=str(fixture_path),
            )

            with self.assertRaises(WRDSServiceError):
                service.get_result_set("Table", [], [])


if __name__ == "__main__":
    unittest.main()


if __name__ == "__main__":
    unittest.main()
