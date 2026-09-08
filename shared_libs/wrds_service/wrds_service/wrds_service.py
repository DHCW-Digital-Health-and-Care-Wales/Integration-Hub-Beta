"""SOAP client for the WRDS (Welsh Reference Data Service) GetResultSet operation.

Standalone client, not related to soap_sender/soap_subscription_sender.

Confirmed calling pattern for Core Reference translation: one GetResultSet call per HL7 message,
filtering only on FromSystem/ToSystem and retrieving FromCode/type/ToCode for every row; each coded
field is then translated client-side via get_to_code(), with no further network calls.
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Type

import requests
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException

logger = logging.getLogger(__name__)

_SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
_MES_NS = "http://www.wales.nhs.uk/namespaces/MessageRelease2"
_NRDS_NS = "http://www.wales.nhs.uk/nrds"


class WRDSServiceError(Exception):
    """Raised on SOAP fault / transport / timeout / parsing failures calling the WRDS service."""


class WRDSService:
    """SOAP client for the WRDS GetResultSet operation.

    Args:
        endpoint_url: Full SOAP POST endpoint URL (not the ``?wsdl`` URL).
        timeout_seconds: HTTP request timeout, in seconds.
        client_cert_path: Optional path to a PEM client certificate for mTLS.
        fixture_file_path: Optional path to a local file containing a raw SOAP `GetResultSetResponse`
            body (e.g. captured from a real WRDS call). When set, `get_result_set()` parses this file
            instead of making any network call — used for local development/testing when the real
            WRDS endpoint is unreachable (e.g. no VPN route).
    """

    def __init__(
        self,
        endpoint_url: str,
        timeout_seconds: int = 30,
        client_cert_path: Optional[str] = None,
        fixture_file_path: Optional[str] = None,
    ) -> None:
        self._endpoint_url = endpoint_url
        self._timeout_seconds = timeout_seconds
        self._client_cert_path = client_cert_path
        self._fixture_file_path = fixture_file_path
        self._session = self._create_session()

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update({"Content-Type": "text/xml; charset=utf-8"})
        return session

    def get_result_set(
        self,
        lookup_table_name: str,
        attributes: list[tuple[str, str]],
        attributes_to_retrieve: list[str],
        exact_match: bool = True,
    ) -> list[dict[str, str]]:
        """Call GetResultSet and return the parsed result rows.

        Builds a request with one AttributeValuePair per ``(name, value)`` entry in `attributes`, one
        AttributeToRetrieve per entry in `attributes_to_retrieve`, and the given LookupTable/ExactMatch.

        Note: response attribute names can differ in casing from the request (e.g. requesting "type"
        can come back as "Type") — callers should compare names case-insensitively, as get_to_code()
        does below.

        Args:
            lookup_table_name: WRDS LookupTable name, e.g. "FioranoCodeTranslation".
            attributes: Filter attribute ``(name, value)`` pairs, e.g. ``[("FromSystem", "349")]``.
            attributes_to_retrieve: Attribute names to retrieve, e.g. ``["FromCode", "type", "ToCode"]``.
            exact_match: Whether WRDS should perform an exact (vs. fuzzy) match.

        Returns:
            One dict per ``<Row>`` in the response, mapping each retrieved attribute name to its value.

        Raises:
            WRDSServiceError: On SOAP fault, transport, timeout, or response-parsing failures.
        """
        if self._fixture_file_path:
            return self._read_fixture_result_set(self._fixture_file_path, lookup_table_name, attributes)

        envelope = _build_get_result_set_envelope(
            lookup_table_name, attributes, attributes_to_retrieve, exact_match
        )
        logger.info("%s", envelope)
        kwargs: dict[str, Any] = {
            "data": envelope.encode("utf-8"),
            "timeout": self._timeout_seconds,
        }
        if self._client_cert_path:
            kwargs["cert"] = self._client_cert_path

        try:
            response = self._session.post(self._endpoint_url, **kwargs)
        except requests.exceptions.Timeout as exc:
            raise WRDSServiceError(
                f"WRDS GetResultSet timed out after {self._timeout_seconds}s"
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            raise WRDSServiceError(f"WRDS GetResultSet connection error: {exc}") from exc

        if response.status_code != 200:
            raise WRDSServiceError(f"WRDS GetResultSet returned HTTP {response.status_code}")

        return _parse_get_result_set_response(response.text)

    def _read_fixture_result_set(
        self,
        fixture_file_path: str,
        lookup_table_name: str,
        attributes: list[tuple[str, str]],
    ) -> list[dict[str, str]]:
        """Load GetResultSet rows from a local fixture file instead of calling WRDS over the network.

        Used for local development only (see `fixture_file_path`) — the filter attributes and lookup
        table name are logged for visibility but not applied to the fixture contents; the fixture file
        holds a raw SOAP `GetResultSetResponse` body (the same shape as a real HTTP response, e.g.
        captured from a real WRDS call) and is parsed with the same `_parse_get_result_set_response()`
        used for real responses — the entire row list found in it is returned as-is (get_to_code()
        already filters client-side by FromCode/type, so an unfiltered fixture behaves the same as a
        real filtered response).

        Raises:
            WRDSServiceError: If the fixture file is missing/unreadable, or its contents cannot be
                parsed as a SOAP GetResultSetResponse (invalid XML, SOAP fault, missing body).
        """
        logger.info(
            "Using local WRDS fixture '%s' instead of a network call (lookup_table='%s', attributes=%s)",
            fixture_file_path,
            lookup_table_name,
            attributes,
        )
        try:
            with open(fixture_file_path, encoding="utf-8") as fixture_file:
                response_text = fixture_file.read()
        except OSError as exc:
            raise WRDSServiceError(f"WRDS local fixture file not found or unreadable: {exc}") from exc

        return _parse_get_result_set_response(response_text)

    def get_to_code(
        self,
        rows: list[dict[str, str]],
        from_code: str,
        reference_type: str,
    ) -> str:
        """Client-side filter over rows already fetched via get_result_set() — makes no network call.

        Args:
            rows: Row list previously returned by get_result_set().
            from_code: The source code to translate, e.g. the raw PID field value.
            reference_type: The reference-data category, e.g. "Sex", "Marital Status".

        Returns:
            The ToCode value for the row matching FromCode == from_code and type == reference_type
            (attribute names compared case-insensitively), or "" if no such row exists — the same
            outcome as a matching row with an empty ToCode value.
        """
        for row in rows:
            row_ci = {name.casefold(): value for name, value in row.items()}
            if row_ci.get("fromcode") == from_code and row_ci.get("type") == reference_type:
                return row_ci.get("tocode") or ""
        return ""

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> "WRDSService":
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[Any],
    ) -> None:
        self.close()


def _build_get_result_set_envelope(
    lookup_table_name: str,
    attributes: list[tuple[str, str]],
    attributes_to_retrieve: list[str],
    exact_match: bool,
) -> str:
    attribute_value_pairs_xml = "".join(
        f"""
      <AttributeValuePair>
        <Attribute>
          <Id></Id>
          <Name>{_xml_escape(name)}</Name>
          <Namespace>{_NRDS_NS}</Namespace>
          <Description></Description>
        </Attribute>
        <Value>{_xml_escape(value)}</Value>
      </AttributeValuePair>"""
        for name, value in attributes
    )
    attributes_to_retrieve_xml = "".join(
        f"""
      <AttributeToRetrieve>
        <Id></Id>
        <Name>{_xml_escape(name)}</Name>
        <Namespace>{_NRDS_NS}</Namespace>
      </AttributeToRetrieve>"""
        for name in attributes_to_retrieve
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<soap:Envelope xmlns:soap="{_SOAP_NS}">\n'
        "  <soap:Body>\n"
        f'    <GetResultSetRequest xmlns="{_MES_NS}">'
        f"{attribute_value_pairs_xml}\n"
        "      <LookupTable>\n"
        "        <Id></Id>\n"
        f"        <Name>{_xml_escape(lookup_table_name)}</Name>\n"
        f"        <Namespace>{_NRDS_NS}</Namespace>\n"
        "      </LookupTable>"
        f"{attributes_to_retrieve_xml}\n"
        f"      <ExactMatch>{1 if exact_match else 0}</ExactMatch>\n"
        "    </GetResultSetRequest>\n"
        "  </soap:Body>\n"
        "</soap:Envelope>"
    )


def _xml_escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _parse_get_result_set_response(response_text: str) -> list[dict[str, str]]:
    try:
        root = ET.fromstring(response_text)
    except ET.ParseError as exc:
        raise WRDSServiceError(f"WRDS GetResultSet response is not valid XML: {exc}") from exc
    except DefusedXmlException as exc:
        raise WRDSServiceError(
            "Rejected WRDS GetResultSet response containing a malicious XML construct"
        ) from exc

    body = root.find(f"{{{_SOAP_NS}}}Body")
    if body is None:
        raise WRDSServiceError("WRDS GetResultSet response missing SOAP Body")

    fault = body.find(f"{{{_SOAP_NS}}}Fault")
    if fault is not None:
        fault_string = fault.findtext("faultstring", default="")
        raise WRDSServiceError(f"WRDS GetResultSet SOAP fault: {fault_string}")

    # GetResultSetResponse (and its Row/AttributeValuePair/... children) are declared in the
    # MessageRelease2 namespace in the real service response, so lookups must be
    # namespace-qualified to work against the real WRDS endpoint.
    response_elem = body.find(f"{{{_MES_NS}}}GetResultSetResponse")
    if response_elem is None:
        raise WRDSServiceError("WRDS GetResultSet response missing GetResultSetResponse")

    rows: list[dict[str, str]] = []
    for row_elem in response_elem.findall(f"{{{_MES_NS}}}Row"):
        values: dict[str, str] = {}
        for avp in row_elem.findall(f"{{{_MES_NS}}}AttributeValuePair"):
            name = avp.findtext(f"{{{_MES_NS}}}Attribute/{{{_MES_NS}}}Name")
            value = avp.findtext(f"{{{_MES_NS}}}Value") or ""
            if name:
                values[name] = value
        rows.append(values)
    return rows
