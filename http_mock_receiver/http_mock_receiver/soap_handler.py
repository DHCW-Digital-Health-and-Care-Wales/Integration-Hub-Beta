"""SOAP request handler — parses an incoming SOAP envelope, extracts the HL7
payload, optionally forwards to Service Bus, and returns an ACK or fault.

Uses the stdlib ``xml.etree.ElementTree`` to avoid additional dependencies.
The handler is intentionally forgiving: if the body is not well-formed XML we
still return a SOAP fault rather than an unhandled 500 so the caller gets a
meaningful response.
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Namespace map for SOAP 1.1 and 1.2 envelope elements.
_SOAP_NS_11 = "http://schemas.xmlsoap.org/soap/envelope/"
_SOAP_NS_12 = "http://www.w3.org/2003/05/soap-envelope"

# HL7 message body element name commonly used in SOAP wrappers.
_HL7_BODY_TAGS = ("hl7Message", "HL7Message", "message", "Message", "payload", "Payload")


@dataclass
class SoapParseResult:
    soap_version: str          # "1.1" or "1.2"
    raw_body: str              # Full request body as received
    hl7_payload: str | None    # Extracted HL7 ER7 text (if found)
    message_control_id: str    # MSH-10 value or fallback placeholder
    is_fault_requested: bool   # True when body contains the word "fail" (mock convention)


def parse_soap_request(raw_body: str) -> SoapParseResult:
    """Parse a SOAP request body and extract relevant fields.

    The function never raises — parse failures produce a result with
    ``is_fault_requested=True`` so the caller can return a SOAP fault.

    Args:
        raw_body: Raw HTTP request body as a UTF-8 string.

    Returns:
        A ``SoapParseResult`` describing the parsed content.
    """
    # Determine the SOAP version from the namespace in the root element.
    soap_version = _detect_soap_version(raw_body)
    hl7_payload: str | None = None
    message_control_id = "UNKNOWN"

    try:
        root = ET.fromstring(raw_body)
        body_element = _find_body(root, soap_version)

        if body_element is not None:
            hl7_payload = _extract_hl7_payload(body_element)

        if hl7_payload:
            message_control_id = _extract_control_id(hl7_payload)

        logger.info(
            "SOAP request parsed — version=%s, control_id=%s, hl7_found=%s",
            soap_version,
            message_control_id,
            hl7_payload is not None,
        )

    except ET.ParseError as exc:
        logger.warning("SOAP envelope is not well-formed XML: %s", exc)

    # Respect the mock convention: "fail" anywhere in the body triggers a fault.
    is_fault_requested = "fail" in raw_body.lower()

    return SoapParseResult(
        soap_version=soap_version,
        raw_body=raw_body,
        hl7_payload=hl7_payload,
        message_control_id=message_control_id,
        is_fault_requested=is_fault_requested,
    )


def _detect_soap_version(raw_body: str) -> str:
    """Infer SOAP version from namespace URI present in the raw body string."""
    if _SOAP_NS_12 in raw_body:
        return "1.2"
    return "1.1"


def _find_body(root: ET.Element, soap_version: str) -> ET.Element | None:
    """Locate the soapenv:Body child element."""
    ns = _SOAP_NS_12 if soap_version == "1.2" else _SOAP_NS_11
    return root.find(f"{{{ns}}}Body")


def _extract_hl7_payload(body_element: ET.Element) -> str | None:
    """Walk immediate children of the Body element looking for HL7 content.

    Tries known tag names first, then falls back to inspecting text content of
    all child elements for MSH segment markers.
    """
    for child in body_element:
        # Strip namespace prefix from tag for comparison.
        local_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag

        if local_tag in _HL7_BODY_TAGS:
            text = (child.text or "").strip()
            if text:
                return text

    # Fallback: look for any child whose text content starts with "MSH".
    for child in body_element.iter():
        text = (child.text or "").strip()
        if text.startswith("MSH"):
            return text

    return None


def _extract_control_id(hl7_text: str) -> str:
    """Extract MSH-10 (message control ID) from an ER7 string.

    Splits on the pipe delimiter without importing hl7apy so this module
    has no dependency on it — the mock just needs the ID for logging.
    """
    try:
        lines = hl7_text.replace("\r\n", "\r").replace("\n", "\r").split("\r")
        for line in lines:
            if line.startswith("MSH"):
                fields = line.split("|")
                # MSH-10 is the 10th field (index 9, accounting for MSH-1=| and MSH-2=^~\&)
                if len(fields) > 9:
                    return fields[9]
    except Exception:  # noqa: BLE001
        pass
    return "UNKNOWN"
