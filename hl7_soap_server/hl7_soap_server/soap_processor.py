from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Iterable, List

# Element/tostring are only used to build and serialize trusted output XML below;
# untrusted SOAP input is always parsed via defusedxml.ElementTree.fromstring.
from xml.etree.ElementTree import Element as XmlElement  # nosec B405
from xml.etree.ElementTree import tostring  # nosec B405

from defusedxml.ElementTree import fromstring
from event_logger_lib.event_logger import EventLogger
from hl7_validation import XmlValidationError, validate_xml, xml_to_er7
from hl7_validation.schemas import get_schema_xsd_path_for
from message_bus_lib.message_sender_client import MessageSenderClient
from message_bus_lib.message_store_client import MessageStoreClient
from message_bus_lib.metadata_utils import (
    CORRELATION_ID_KEY,
    MESSAGE_RECEIVED_AT_KEY,
    SOURCE_SYSTEM_KEY,
)
from metric_sender_lib.metric_sender import MetricSender

from hl7_soap_server.custom_message_properties import build_common_properties

logger = logging.getLogger(__name__)
SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"


@dataclass
class SoapFault(Exception):
    fault_code: str
    fault_string: str
    http_status: int


class SoapMessageProcessor:
    def __init__(
        self,
        sender_client: MessageSenderClient,
        event_logger: EventLogger,
        metric_sender: MetricSender,
        message_store_client: MessageStoreClient,
        workflow_id: str,
        egress_session_id: str,
        schema_group: str,
        allowed_hl7_structures: List[str],
        allowed_assigning_authorities: List[str],
    ) -> None:
        self.sender_client = sender_client
        self.event_logger = event_logger
        self.metric_sender = metric_sender
        self.message_store_client = message_store_client
        self.workflow_id = workflow_id
        self.egress_session_id = egress_session_id
        self.schema_group = schema_group
        self.allowed_hl7_structures = set(allowed_hl7_structures)
        self.allowed_assigning_authorities = set(allowed_assigning_authorities)

    def process(self, incoming_soap_xml: str) -> tuple[int, str]:
        self.event_logger.log_message_received(incoming_soap_xml)
        self.metric_sender.send_message_received_metric()

        try:
            payload_element = _extract_soap_business_payload(incoming_soap_xml)
            structure_id = _local_name(payload_element.tag)

            if structure_id not in self.allowed_hl7_structures:
                raise SoapFault(
                    "Client.Validation",
                    (
                        f"Unsupported HL7 message structure '{structure_id}'. "
                        f"Allowed values: {', '.join(sorted(self.allowed_hl7_structures))}"
                    ),
                    400,
                )

            payload_xml = tostring(payload_element, encoding="unicode")

            try:
                xsd_path = get_schema_xsd_path_for(self.schema_group, structure_id)
            except ValueError as exc:
                logger.error(
                    "Schema mapping error for group '%s' and structure '%s': %s",
                    self.schema_group,
                    structure_id,
                    exc,
                )
                raise SoapFault("Server.Configuration", "SOAP schema mapping is not configured.", 500) from exc

            try:
                validate_xml(payload_xml, xsd_path)
                self.event_logger.log_validation_result(
                    incoming_soap_xml,
                    f"XML schema validation passed for structure '{structure_id}'",
                    is_success=True,
                )
            except XmlValidationError as exc:
                raise SoapFault("Client.Validation", f"Payload schema validation failed: {exc}", 400) from exc

            sending_authority = _extract_assigning_authority(payload_element)
            if sending_authority not in self.allowed_assigning_authorities:
                raise SoapFault(
                    "Client.Authorization",
                    (
                        f"Assigning authority '{sending_authority}' is not authorised. "
                        f"Allowed values: {', '.join(sorted(self.allowed_assigning_authorities))}"
                    ),
                    403,
                )

            try:
                er7_payload = xml_to_er7(payload_xml)
            except Exception as exc:
                raise SoapFault("Client.Validation", "Unable to convert XML payload to ER7 format.", 400) from exc

            tracking_metadata_properties = build_common_properties(self.workflow_id, sending_authority)
            correlation_id = tracking_metadata_properties.get(CORRELATION_ID_KEY)
            message_control_id = _extract_message_control_id(payload_element)

            self._send_to_message_store(
                tracking_metadata_properties=tracking_metadata_properties,
                raw_payload=incoming_soap_xml,
                xml_payload=payload_xml,
            )

            self.sender_client.send_text_message(
                er7_payload,
                tracking_metadata_properties,
                message_id=message_control_id or None,
            )
            self.metric_sender.send_message_sent_metric()

            self.event_logger.log_message_processed(
                incoming_soap_xml,
                f"SOAP payload validated and forwarded (structure: {structure_id})",
                correlation_id=correlation_id,
            )

            return 200, build_soap_success_response(message_control_id)
        except SoapFault as fault:
            logger.warning("SOAP request rejected: %s", fault.fault_string)
            self.event_logger.log_validation_result(incoming_soap_xml, fault.fault_string, is_success=False)
            self.event_logger.log_message_failed(incoming_soap_xml, fault.fault_string, "SOAP request rejected")
            return fault.http_status, build_soap_fault_response(fault.fault_code, fault.fault_string)
        except Exception as exc:
            logger.exception("Unexpected SOAP processing error: %s", exc)
            error_message = "Unexpected server error while processing SOAP request."
            self.event_logger.log_message_failed(incoming_soap_xml, error_message, "Unhandled SOAP server error")
            return 500, build_soap_fault_response("Server", error_message)

    def _send_to_message_store(
        self,
        tracking_metadata_properties: Dict[str, str],
        raw_payload: str,
        xml_payload: str,
    ) -> None:
        # Store failures must not block sender acknowledgements.
        try:
            self.message_store_client.send_to_store(
                message_received_at=tracking_metadata_properties.get(MESSAGE_RECEIVED_AT_KEY, ""),
                correlation_id=tracking_metadata_properties.get(CORRELATION_ID_KEY, ""),
                source_system=tracking_metadata_properties.get(SOURCE_SYSTEM_KEY, ""),
                raw_payload=raw_payload,
                session_id=self.egress_session_id,
                xml_payload=xml_payload,
            )
        except Exception as exc:
            logger.error("Failed to send SOAP message to message store: %s", exc)


def _local_name(tag: str) -> str:
    if tag.startswith("{"):
        _, local_name = tag[1:].split("}", 1)
        return local_name
    return tag


def _iter_by_local_name(root: XmlElement, local_name: str) -> Iterable[XmlElement]:
    for element in root.iter():
        if _local_name(element.tag) == local_name:
            yield element


def _extract_soap_business_payload(incoming_soap_xml: str) -> XmlElement:
    try:
        root = fromstring(incoming_soap_xml)
    except Exception as exc:
        raise SoapFault("Client", "Malformed SOAP XML request.", 400) from exc

    if _local_name(root.tag) != "Envelope":
        raise SoapFault("Client", "SOAP Envelope element is missing.", 400)

    body_element = next(iter(_iter_by_local_name(root, "Body")), None)
    if body_element is None:
        raise SoapFault("Client", "SOAP Body element is missing.", 400)

    payload_children = [child for child in list(body_element) if isinstance(child.tag, str)]
    if len(payload_children) != 1:
        raise SoapFault("Client", "SOAP Body must contain exactly one business payload element.", 400)

    return payload_children[0]


def _extract_first_text(parent: XmlElement, local_names: List[str]) -> str | None:
    current_nodes: List[XmlElement] = [parent]

    for expected_name in local_names:
        next_nodes: List[XmlElement] = []
        for node in current_nodes:
            for child in list(node):
                if isinstance(child.tag, str) and _local_name(child.tag) == expected_name:
                    next_nodes.append(child)
        if not next_nodes:
            return None
        current_nodes = next_nodes

    for node in current_nodes:
        if node.text and node.text.strip():
            return node.text.strip()

    return None


def _extract_assigning_authority(payload_element: XmlElement) -> str:
    authority_from_msh3 = _extract_first_text(payload_element, ["MSH", "MSH.3", "HD.1"])
    authority_from_msh4 = _extract_first_text(payload_element, ["MSH", "MSH.4", "HD.1"])
    authority_from_pid3 = _extract_first_text(payload_element, ["PID", "PID.3", "CX.4", "HD.1"])

    for authority in [authority_from_msh3, authority_from_msh4, authority_from_pid3]:
        if authority:
            return authority

    raise SoapFault("Client.Validation", "Unable to determine assigning authority from payload.", 400)


def _extract_message_control_id(payload_element: XmlElement) -> str:
    control_id = _extract_first_text(payload_element, ["MSH", "MSH.10"])
    return control_id or ""


def build_soap_success_response(message_control_id: str) -> str:
    envelope = (
        f'<soapenv:Envelope xmlns:soapenv="{SOAP_NS}">'
        "<soapenv:Body>"
        "<AckResponse>"
        "<Status>Success</Status>"
        f"<MessageControlId>{message_control_id}</MessageControlId>"
        "</AckResponse>"
        "</soapenv:Body>"
        "</soapenv:Envelope>"
    )
    return envelope


def build_soap_fault_response(fault_code: str, fault_string: str) -> str:
    escaped_fault_string = (
        fault_string.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
    envelope = (
        f'<soapenv:Envelope xmlns:soapenv="{SOAP_NS}">'
        "<soapenv:Body>"
        "<soapenv:Fault>"
        f"<faultcode>{fault_code}</faultcode>"
        f"<faultstring>{escaped_fault_string}</faultstring>"
        "</soapenv:Fault>"
        "</soapenv:Body>"
        "</soapenv:Envelope>"
    )
    return envelope
