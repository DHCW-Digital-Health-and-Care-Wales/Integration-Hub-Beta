"""SOAP request handler — parses an incoming SOAP envelope, extracts the HL7
payload, optionally forwards to Service Bus, and returns an ACK or fault.

Uses ``defusedxml`` to parse XML safely and guard against XXE injection.
The handler is intentionally forgiving: if the body is not well-formed XML we
log the parse error and still return an ACK/fault based on the mock "fail"
trigger so callers always get a valid response.
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import defusedxml
import defusedxml.ElementTree as SafeET

logger = logging.getLogger(__name__)

# Namespace map for SOAP 1.1 and 1.2 envelope elements.
_SOAP_NS_11 = "http://schemas.xmlsoap.org/soap/envelope/"
_SOAP_NS_12 = "http://www.w3.org/2003/05/soap-envelope"

# HL7 message body element name commonly used in SOAP wrappers.
_HL7_BODY_TAGS = ("hl7Message", "HL7Message", "message", "Message", "payload", "Payload")

# WIS CaptureFromFiorona payload element — matched by local name since the WIS
# envelope uses its own namespaces (not the standard SOAP envelope namespace).
_WIS_PAYLOAD_TAG = "inputString"


@dataclass
class SoapParseResult:
    soap_version: str          # "1.1" or "1.2"
    raw_body: str              # Full request body as received
    hl7_payload: str | None    # Extracted HL7 ER7 text (if found)
    wis_payload: str | None    # Extracted WIS CaptureFromFiorona inputString text (if found)
    is_well_formed_xml: bool   # True when raw_body parsed as XML without error
    message_control_id: str    # MSH-10 value or fallback placeholder
    ack_code: str              # "AA", "AE", or "AR"
    is_fault_requested: bool   # True when ack_code is AE or AR


def parse_soap_request(raw_body: str) -> SoapParseResult:
    """Parse a SOAP request body and extract relevant fields.

    The function never raises. If the body is not well-formed XML, the parse
    error is logged and the result is returned with ``hl7_payload=None``.

    The mock fault convention is separate: ``is_fault_requested`` is True only
    when the word "fail" appears anywhere in the raw request body.

    Args:
        raw_body: Raw HTTP request body as a UTF-8 string.

    Returns:
        A ``SoapParseResult`` describing the parsed content.
    """
    # Determine the SOAP version from the namespace in the root element.
    soap_version = _detect_soap_version(raw_body)
    hl7_payload: str | None = None
    wis_payload: str | None = None
    is_well_formed_xml = False
    message_control_id = "UNKNOWN"

    try:
        # Use defusedxml to prevent XXE (XML external entity) injection attacks.
        root = SafeET.fromstring(raw_body)
        is_well_formed_xml = True
        body_element = _find_body(root, soap_version)

        if body_element is not None:
            hl7_payload = _extract_hl7_payload(body_element)

        if not hl7_payload:
            wis_payload = _extract_wis_payload(root)

        if hl7_payload:
            message_control_id = _extract_control_id(hl7_payload)

        logger.info(
            "SOAP request parsed — version=%s, control_id=%s, hl7_found=%s, wis_found=%s",
            soap_version,
            message_control_id,
            hl7_payload is not None,
            wis_payload is not None,
        )

    except (ET.ParseError, defusedxml.DTDForbidden, defusedxml.EntitiesForbidden,
            defusedxml.ExternalReferenceForbidden, defusedxml.NotSupportedError) as exc:
        logger.warning("SOAP envelope is not well-formed XML: %s", exc)

    # Mirror the HL7 mock receiver semantics: reject beats fail, fail beats accept.
    lower_message = raw_body.lower()
    if "reject" in lower_message:
        ack_code = "AR"
    elif "fail" in lower_message:
        ack_code = "AE"
    else:
        ack_code = "AA"

    is_fault_requested = ack_code != "AA"

    return SoapParseResult(
        soap_version=soap_version,
        raw_body=raw_body,
        hl7_payload=hl7_payload,
        wis_payload=wis_payload,
        is_well_formed_xml=is_well_formed_xml,
        message_control_id=message_control_id,
        ack_code=ack_code,
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


def _extract_wis_payload(root: ET.Element) -> str | None:
    """Extract the WIS CaptureFromFiorona ``inputString`` payload, if present.

    Matched by local element name (ignoring namespace) since the WIS envelope
    uses its own namespaces rather than the standard SOAP envelope namespace.
    """
    for elem in root.iter():
        local_tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if local_tag == _WIS_PAYLOAD_TAG:
            text = (elem.text or "").strip()
            if text:
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
