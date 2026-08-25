"""SOAP envelope content adapter - same unwrap/response logic as hl7_soap_server."""
from __future__ import annotations

# Only used to build and serialize trusted output XML below; untrusted SOAP
# input is always parsed via defusedxml.ElementTree.fromstring.
from xml.etree.ElementTree import Element as XmlElement  # nosec B405
from xml.etree.ElementTree import tostring  # nosec B405

from defusedxml.ElementTree import fromstring

from rest_server.errors import RequestError
from rest_server.xml_utils import find_first_text, local_name

from .base import ExtractedPayload

SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"


class SoapContentAdapter:
    content_type = "text/xml; charset=utf-8"

    def extract(self, raw_body: str) -> ExtractedPayload:
        try:
            root = fromstring(raw_body)
        except Exception as exc:
            raise RequestError("Client", "Malformed SOAP XML request.", 400) from exc

        if local_name(root.tag) != "Envelope":
            raise RequestError("Client", "SOAP Envelope element is missing.", 400)

        body_element = next((el for el in root.iter() if local_name(el.tag) == "Body"), None)
        if body_element is None:
            raise RequestError("Client", "SOAP Body element is missing.", 400)

        payload_children = [child for child in list(body_element) if isinstance(child.tag, str)]
        if len(payload_children) != 1:
            raise RequestError("Client", "SOAP Body must contain exactly one business payload element.", 400)

        payload_element = payload_children[0]
        payload_xml = tostring(payload_element, encoding="unicode")

        return ExtractedPayload(
            payload_xml=payload_xml,
            structure_id=local_name(payload_element.tag),
            source_identifier=self._require_assigning_authority(payload_element),
            message_control_id=find_first_text(payload_element, ["MSH", "MSH.10"]),
        )

    def _require_assigning_authority(self, payload_element: XmlElement) -> str:
        candidate_paths = (
            ["MSH", "MSH.3", "HD.1"],
            ["MSH", "MSH.4", "HD.1"],
            ["PID", "PID.3", "CX.4", "HD.1"],
        )
        for path in candidate_paths:
            value = find_first_text(payload_element, path)
            if value:
                return value
        raise RequestError("Client.Validation", "Unable to determine assigning authority from payload.", 400)

    def build_success_response(self, message_control_id: str) -> str:
        escaped_message_control_id = _escape(message_control_id or "")
        return (
            f'<soapenv:Envelope xmlns:soapenv="{SOAP_NS}" xmlns:tns="urn:inthub:rest-server">'
            "<soapenv:Body>"
            "<tns:AckResponse>"
            "<Status>Success</Status>"
            f"<MessageControlId>{escaped_message_control_id}</MessageControlId>"
            "</tns:AckResponse>"
            "</soapenv:Body>"
            "</soapenv:Envelope>"
        )

    def build_error_response(self, error_code: str, error_message: str) -> str:
        escaped_code = _escape(error_code)
        escaped_message = _escape(error_message)
        return (
            f'<soapenv:Envelope xmlns:soapenv="{SOAP_NS}">'
            "<soapenv:Body>"
            "<soapenv:Fault>"
            f"<faultcode>{escaped_code}</faultcode>"
            f"<faultstring>{escaped_message}</faultstring>"
            "</soapenv:Fault>"
            "</soapenv:Body>"
            "</soapenv:Envelope>"
        )


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
