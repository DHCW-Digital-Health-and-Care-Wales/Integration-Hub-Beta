"""Builds well-formed SOAP response envelopes.

Produces minimal but valid envelopes — sufficient for a mock receiver.
Supports SOAP 1.1 and SOAP 1.2; the version is selected by the caller via
``soap_version``.
"""
from __future__ import annotations

# SOAP 1.1 namespace — the most common version in NHS Wales integrations.
_SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
_CONTENT_TYPE_SOAP11 = "text/xml; charset=utf-8"

# SOAP 1.2 namespace — supported as a future extension.
_SOAP_NS_12 = "http://www.w3.org/2003/05/soap-envelope"
_CONTENT_TYPE_SOAP12 = "application/soap+xml; charset=utf-8"


def build_ack_response(message_control_id: str, soap_version: str = "1.1") -> tuple[str, str]:
    """Return a (body, content_type) tuple for a successful SOAP acknowledgement.

    Args:
        message_control_id: The MSH-10 control ID extracted from the HL7 message.
        soap_version: "1.1" (default) or "1.2".

    Returns:
        Tuple of (XML string, Content-Type header value).
    """
    ns, content_type = _resolve_version(soap_version)
    body = (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<soapenv:Envelope xmlns:soapenv="{ns}">\n'
        f"  <soapenv:Header/>\n"
        f"  <soapenv:Body>\n"
        f"    <AcknowledgementResponse>\n"
        f"      <Status>AA</Status>\n"
        f"      <MessageControlID>{_escape(message_control_id)}</MessageControlID>\n"
        f"      <Detail>Message accepted by HTTP mock receiver</Detail>\n"
        f"    </AcknowledgementResponse>\n"
        f"  </soapenv:Body>\n"
        f"</soapenv:Envelope>"
    )
    return body, content_type


def build_fault_response(fault_detail: str, soap_version: str = "1.1") -> tuple[str, str]:
    """Return a (body, content_type) tuple for a SOAP fault response.

    Args:
        fault_detail: Human-readable description of the failure.
        soap_version: "1.1" (default) or "1.2".

    Returns:
        Tuple of (XML string, Content-Type header value).
    """
    ns, content_type = _resolve_version(soap_version)

    if soap_version == "1.2":
        # SOAP 1.2 fault structure differs from 1.1.
        body = (
            f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<soapenv:Envelope xmlns:soapenv="{ns}">\n'
            f"  <soapenv:Body>\n"
            f"    <soapenv:Fault>\n"
            f"      <soapenv:Code><soapenv:Value>soapenv:Receiver</soapenv:Value></soapenv:Code>\n"
            f"      <soapenv:Reason><soapenv:Text>Message processing failed</soapenv:Text></soapenv:Reason>\n"
            f"      <soapenv:Detail>{_escape(fault_detail)}</soapenv:Detail>\n"
            f"    </soapenv:Fault>\n"
            f"  </soapenv:Body>\n"
            f"</soapenv:Envelope>"
        )
    else:
        body = (
            f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<soapenv:Envelope xmlns:soapenv="{ns}">\n'
            f"  <soapenv:Body>\n"
            f"    <soapenv:Fault>\n"
            f"      <faultcode>soapenv:Client</faultcode>\n"
            f"      <faultstring>Message processing failed</faultstring>\n"
            f"      <detail>{_escape(fault_detail)}</detail>\n"
            f"    </soapenv:Fault>\n"
            f"  </soapenv:Body>\n"
            f"</soapenv:Envelope>"
        )
    return body, content_type


def _resolve_version(soap_version: str) -> tuple[str, str]:
    if soap_version == "1.2":
        return _SOAP_NS_12, _CONTENT_TYPE_SOAP12
    return _SOAP_NS, _CONTENT_TYPE_SOAP11


def _escape(text: str) -> str:
    """Minimal XML character escaping for values embedded in response bodies."""
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
    )
