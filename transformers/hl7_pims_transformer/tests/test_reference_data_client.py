import json
import unittest
from typing import Mapping, Optional

import urllib3

from hl7_pims_transformer.clients.reference_data_client import (
    ReferenceDataLookupClient,
    ReferenceDataLookupError,
    ReferenceDataset,
)


class _FakeResponse:
    def __init__(self, status: int, body: Optional[bytes]) -> None:
        self.status = status
        self.data = body if body is not None else b""


class _FakeHttp:
    """Minimal ``urllib3.PoolManager`` stand-in that records the request and returns a canned
    response (or raises a supplied exception)."""

    def __init__(self, response: Optional[_FakeResponse] = None, error: Optional[Exception] = None) -> None:
        self._response = response
        self._error = error
        self.last_url: Optional[str] = None
        self.last_headers: Optional[Mapping[str, str]] = None

    def request(
        self, method: str, url: str, *, headers: Mapping[str, str], timeout: object
    ) -> _FakeResponse:
        self.last_url = url
        self.last_headers = headers
        if self._error is not None:
            raise self._error
        assert self._response is not None
        return self._response


def _ok_body(target_code: str) -> bytes:
    return json.dumps({"dataset": "gender", "sourceCode": "F", "targetCode": target_code}).encode("utf-8")


class TestReferenceDataLookupClient(unittest.TestCase):
    def test_successful_lookup_returns_target_code(self) -> None:
        http = _FakeHttp(_FakeResponse(200, _ok_body("2")))
        client = ReferenceDataLookupClient("http://ref-api:8080", http=http)

        result = client.lookup(ReferenceDataset.GENDER, "F")

        self.assertEqual(result, "2")
        self.assertEqual(http.last_url, "http://ref-api:8080/lookup/gender/F")

    def test_base_url_trailing_slash_is_normalised(self) -> None:
        http = _FakeHttp(_FakeResponse(200, _ok_body("2")))
        client = ReferenceDataLookupClient("http://ref-api:8080/", http=http)

        client.lookup(ReferenceDataset.GENDER, "F")

        self.assertEqual(http.last_url, "http://ref-api:8080/lookup/gender/F")

    def test_source_code_is_url_encoded(self) -> None:
        http = _FakeHttp(_FakeResponse(200, _ok_body("2")))
        client = ReferenceDataLookupClient("http://ref-api:8080", http=http)

        client.lookup(ReferenceDataset.GENDER, "a/b")

        self.assertEqual(http.last_url, "http://ref-api:8080/lookup/gender/a%2Fb")

    def test_api_key_is_sent_as_header(self) -> None:
        http = _FakeHttp(_FakeResponse(200, _ok_body("2")))
        client = ReferenceDataLookupClient("http://ref-api:8080", api_key="secret", http=http)

        client.lookup(ReferenceDataset.GENDER, "F")

        assert http.last_headers is not None
        self.assertEqual(http.last_headers.get("X-API-Key"), "secret")

    def test_missing_base_url_raises(self) -> None:
        client = ReferenceDataLookupClient("", http=_FakeHttp(_FakeResponse(200, _ok_body("2"))))

        with self.assertRaises(ReferenceDataLookupError):
            client.lookup(ReferenceDataset.GENDER, "F")

    def test_blank_source_code_raises(self) -> None:
        client = ReferenceDataLookupClient("http://ref-api:8080", http=_FakeHttp(_FakeResponse(200, _ok_body("2"))))

        with self.assertRaises(ReferenceDataLookupError):
            client.lookup(ReferenceDataset.GENDER, "   ")

    def test_404_raises_no_mapping(self) -> None:
        client = ReferenceDataLookupClient("http://ref-api:8080", http=_FakeHttp(_FakeResponse(404, b"")))

        with self.assertRaises(ReferenceDataLookupError):
            client.lookup(ReferenceDataset.GENDER, "F")

    def test_server_error_raises(self) -> None:
        client = ReferenceDataLookupClient("http://ref-api:8080", http=_FakeHttp(_FakeResponse(500, b"")))

        with self.assertRaises(ReferenceDataLookupError):
            client.lookup(ReferenceDataset.GENDER, "F")

    def test_network_error_raises(self) -> None:
        error = urllib3.exceptions.MaxRetryError(pool=None, url="http://ref-api:8080", reason=None)  # type: ignore[arg-type]
        client = ReferenceDataLookupClient("http://ref-api:8080", http=_FakeHttp(error=error))

        with self.assertRaises(ReferenceDataLookupError):
            client.lookup(ReferenceDataset.GENDER, "F")

    def test_unparseable_body_raises(self) -> None:
        client = ReferenceDataLookupClient("http://ref-api:8080", http=_FakeHttp(_FakeResponse(200, b"not-json")))

        with self.assertRaises(ReferenceDataLookupError):
            client.lookup(ReferenceDataset.GENDER, "F")

    def test_missing_target_code_raises(self) -> None:
        body = json.dumps({"dataset": "gender", "sourceCode": "F"}).encode("utf-8")
        client = ReferenceDataLookupClient("http://ref-api:8080", http=_FakeHttp(_FakeResponse(200, body)))

        with self.assertRaises(ReferenceDataLookupError):
            client.lookup(ReferenceDataset.GENDER, "F")

    def test_invalid_format_target_code_raises(self) -> None:
        # Scenario 2: the API returns a value in an unexpected format (contains an HL7 delimiter).
        http = _FakeHttp(_FakeResponse(200, _ok_body("2^BAD")))
        client = ReferenceDataLookupClient("http://ref-api:8080", http=http)

        with self.assertRaises(ReferenceDataLookupError):
            client.lookup(ReferenceDataset.GENDER, "F")

    def test_nhs_status_requires_numeric_code(self) -> None:
        http = _FakeHttp(_FakeResponse(200, _ok_body("AB")))
        client = ReferenceDataLookupClient("http://ref-api:8080", http=http)

        with self.assertRaises(ReferenceDataLookupError):
            client.lookup(ReferenceDataset.NHS_STATUS, "03")


if __name__ == "__main__":
    unittest.main()
