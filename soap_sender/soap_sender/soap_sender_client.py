"""SOAP sender client — wraps HL7 ER7 in a SOAP 1.1 envelope and POSTs it.

Mirrors ``hl7_sender_client.py`` in structure: context manager, retry on
transient failures, raises ``TimeoutError`` or ``ConnectionError`` on failure
so ``application.py`` can map these to Service Bus abandon/retry unchanged.

Envelope formats
----------------
``default``
    Wraps raw ER7 (XML-escaped) inside ``<SendHL7Message><hl7Message>…``.

``wis``
    Converts ER7 to HL7 v2 XML (``urn:hl7-org:v2xml`` namespace), then places
    the XML-escaped result inside the WIS ``CaptureFromFiorona`` body:

    .. code-block:: xml

        <ns1:Envelope xmlns:ns1="http://Cypris.Nhs.Wales.Uk/CaptureFromFiorona/Input">
          <ns1:Body>
            <ns3:CaptureFromFiorona xmlns:ns3="http://Cypris.Nhs.Wales.Uk/">
              <ns3:inputString>…escaped HL7 v2 XML…</ns3:inputString>
            </ns3:CaptureFromFiorona>
          </ns1:Body>
        </ns1:Envelope>
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Type

import requests
from hl7_validation import convert_er7_to_xml

logger = logging.getLogger(__name__)

# SOAP 1.1 namespace — used for the default envelope format.
_SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"

# WIS-specific namespaces for the CaptureFromFiorona envelope.
_WIS_ENV_NS = "http://Cypris.Nhs.Wales.Uk/CaptureFromFiorona/Input"
_WIS_SVC_NS = "http://Cypris.Nhs.Wales.Uk/"


class SOAPSenderClient:
    """HTTP client that wraps HL7 ER7 in a SOAP envelope and POSTs to an endpoint.

    Args:
        endpoint_url: Full URL of the SOAP endpoint (e.g. http://host:8080/soap).
        timeout_seconds: HTTP request timeout.  Matches hl7_sender ACK timeout semantics.
        api_key: Optional API key — added as ``Authorization: ApiKey <key>`` header.
        client_cert_path: Optional path to a PEM client certificate for mTLS.
        envelope_format: ``"wis"`` to use the CaptureFromFiorona envelope (HL7 v2 XML
            payload); any other value uses the default ``<SendHL7Message>`` envelope (ER7).
    """

    def __init__(
        self,
        endpoint_url: str,
        timeout_seconds: int = 30,
        api_key: str | None = None,
        client_cert_path: str | None = None,
        envelope_format: str = "default",
    ) -> None:
        self.endpoint_url = endpoint_url
        self.timeout_seconds = timeout_seconds
        self.client_cert_path = client_cert_path
        self.envelope_format = envelope_format.lower().strip()
        self._session = self._create_session(api_key)

    def _create_session(self, api_key: str | None) -> requests.Session:
        session = requests.Session()
        session.headers.update({"Content-Type": "text/xml; charset=utf-8"})
        if api_key:
            session.headers.update({"Authorization": f"ApiKey {api_key}"})
        return session

    def send_message(self, hl7_message: str, _retry_attempted: bool = False) -> tuple[int, str]:
        """Wrap HL7 in a SOAP envelope and POST to the endpoint.

        Args:
            hl7_message: Raw HL7 ER7 string.
            _retry_attempted: Internal flag — prevents infinite retry loops.

        Returns:
            Tuple of (HTTP status code, response body string).

        Raises:
            TimeoutError: No response within ``timeout_seconds``.
            ConnectionError: Network-level failure.
        """
        if self.envelope_format == "wis":
            envelope = _build_wis_soap_envelope(hl7_message)
        else:
            envelope = _build_soap_envelope(hl7_message)
        kwargs: dict[str, Any] = {
            "data": envelope.encode("utf-8"),
            "timeout": self.timeout_seconds,
        }
        if self.client_cert_path:
            kwargs["cert"] = self.client_cert_path

        try:
            response = self._session.post(self.endpoint_url, **kwargs)
            logger.debug("SOAP response: HTTP %s", response.status_code)
            return response.status_code, response.text

        except requests.exceptions.Timeout:
            if not _retry_attempted:
                logger.warning("SOAP request timed out — retrying with a fresh session...")
                self._session.close()
                self._session = self._create_session(
                    self._session.headers.get("Authorization", "").replace("ApiKey ", "") or None
                )
                return self.send_message(hl7_message, _retry_attempted=True)
            raise TimeoutError(f"No SOAP response within {self.timeout_seconds} seconds")
        except requests.exceptions.ConnectionError as exc:
            raise ConnectionError(f"SOAP connection error: {exc}") from exc

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> "SOAPSenderClient":
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[Any],
    ) -> None:
        self.close()


def _build_soap_envelope(hl7_message: str) -> str:
    """Wrap an HL7 ER7 string in a SOAP 1.1 envelope.

    The HL7 payload is XML-escaped so special characters in ER7 (& < >) do not
    break the envelope structure.
    """
    escaped = (
        hl7_message
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<soapenv:Envelope xmlns:soapenv="{_SOAP_NS}">\n'
        f"  <soapenv:Header/>\n"
        f"  <soapenv:Body>\n"
        f"    <SendHL7Message>\n"
        f"      <hl7Message>{escaped}</hl7Message>\n"
        f"    </SendHL7Message>\n"
        f"  </soapenv:Body>\n"
        f"</soapenv:Envelope>"
    )


def _build_wis_soap_envelope(hl7_er7: str) -> str:
    """Build a WIS CaptureFromFiorona SOAP envelope from an HL7 ER7 string.

    Steps:
    1. Convert ER7 to HL7 v2 XML (``urn:hl7-org:v2xml`` namespace) via
       ``hl7_validation.convert_er7_to_xml``.
    2. XML-escape the resulting XML string so it can be embedded as text content
       inside ``<ns3:inputString>``.
    3. Wrap in the WIS-specific SOAP envelope structure.

    Raises:
        ValueError: If ER7-to-XML conversion fails.
    """
    try:
        hl7_xml = convert_er7_to_xml(hl7_er7)
    except Exception as exc:
        raise ValueError(f"Failed to convert ER7 to HL7 v2 XML for WIS envelope: {exc}") from exc

    escaped = (
        hl7_xml
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<ns1:Envelope xmlns:ns1="{_WIS_ENV_NS}">\n'
        f'  <ns1:Body>\n'
        f'    <ns3:CaptureFromFiorona xmlns:ns3="{_WIS_SVC_NS}">\n'
        f'      <ns3:inputString>{escaped}</ns3:inputString>\n'
        f'    </ns3:CaptureFromFiorona>\n'
        f'  </ns1:Body>\n'
        f'</ns1:Envelope>'
    )
