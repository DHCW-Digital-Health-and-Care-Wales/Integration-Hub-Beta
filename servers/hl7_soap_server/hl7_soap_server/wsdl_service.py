"""Auto-generated WSDL document support for hl7_soap_server.

Builds an accurate, up-to-date WSDL document on demand (``GET /soap?wsdl``),
addressed at whatever host served the request. This means the generated
``soap:address`` always matches the environment the server is running in
(dev/load/prod), with no manual editing required, unlike the previous
hand-authored WSDL under local/sample_messages/.

Note: this module only describes the SOAP *contract* (messages, operations,
binding, address) for client tooling such as SoapUI. It has no influence over
real request handling - all SOAP envelope unwrapping, HL7 schema validation,
business validation, and downstream forwarding is still performed entirely by
SoapMessageProcessor (see soap_processor.py), completely unchanged.

The payload/response elements are declared as unconstrained ``xsd:anyType``
rather than importing the real HL7 2.5 XSDs (shared_libs/hl7_validation/...).
This avoids the fragile relative xsd:include paths that previously broke when
the WSDL was copied outside the repo (e.g. onto a Bastion host) for SoapUI
import; the real, authoritative HL7 structure validation always happens
server-side.

Note: an earlier version of this module generated the WSDL using the Spyne
framework. That was reverted - Spyne 2.14.0 (its latest release) vendors a
copy of `six` that registers a `sys.meta_path` finder using the legacy
`find_module`/`load_module` PEP 302 API, which was removed in Python 3.12,
making it fundamentally incompatible with this project's Python 3.13 target.
"""

from __future__ import annotations

_WSDL_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<definitions name="Hl7SoapServer"
             targetNamespace="urn:inthub:hl7-soap-server"
             xmlns:tns="urn:inthub:hl7-soap-server"
             xmlns:hl7="urn:hl7-org:v2xml"
             xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
             xmlns:xsd="http://www.w3.org/2001/XMLSchema"
             xmlns="http://schemas.xmlsoap.org/wsdl/">

  <types>
    <xsd:schema targetNamespace="urn:hl7-org:v2xml"
                elementFormDefault="qualified">
      <!-- Payload structure is intentionally unconstrained here: the
           authoritative HL7 2.5 XSD validation (schema_group-specific) is
           always performed server-side by SoapMessageProcessor. -->
      <xsd:element name="ADT_A05" type="xsd:anyType"/>
      <xsd:element name="ADT_A39" type="xsd:anyType"/>
    </xsd:schema>

    <xsd:schema targetNamespace="urn:inthub:hl7-soap-server"
                elementFormDefault="qualified">
      <xsd:element name="AckResponse">
        <xsd:complexType>
          <xsd:sequence>
            <xsd:element name="Status" type="xsd:string"/>
            <xsd:element name="MessageControlId" type="xsd:string"/>
          </xsd:sequence>
        </xsd:complexType>
      </xsd:element>
    </xsd:schema>
  </types>

  <message name="SubmitADT_A05Request">
    <part name="payload" element="hl7:ADT_A05"/>
  </message>
  <message name="SubmitADT_A39Request">
    <part name="payload" element="hl7:ADT_A39"/>
  </message>
  <message name="SubmitHL7MessageResponse">
    <part name="ack" element="tns:AckResponse"/>
  </message>
  <message name="SubmitHL7MessageFault">
    <part name="fault" type="xsd:string"/>
  </message>

  <portType name="Hl7SoapServerPortType">
    <operation name="SubmitADT_A05">
      <input message="tns:SubmitADT_A05Request"/>
      <output message="tns:SubmitHL7MessageResponse"/>
      <fault name="ProcessingFault" message="tns:SubmitHL7MessageFault"/>
    </operation>
    <operation name="SubmitADT_A39">
      <input message="tns:SubmitADT_A39Request"/>
      <output message="tns:SubmitHL7MessageResponse"/>
      <fault name="ProcessingFault" message="tns:SubmitHL7MessageFault"/>
    </operation>
  </portType>

  <binding name="Hl7SoapServerBinding" type="tns:Hl7SoapServerPortType">
    <soap:binding style="document" transport="http://schemas.xmlsoap.org/soap/http"/>
    <operation name="SubmitADT_A05">
      <soap:operation soapAction=""/>
      <input><soap:body use="literal"/></input>
      <output><soap:body use="literal"/></output>
      <fault name="ProcessingFault"><soap:fault name="ProcessingFault" use="literal"/></fault>
    </operation>
    <operation name="SubmitADT_A39">
      <soap:operation soapAction=""/>
      <input><soap:body use="literal"/></input>
      <output><soap:body use="literal"/></output>
      <fault name="ProcessingFault"><soap:fault name="ProcessingFault" use="literal"/></fault>
    </operation>
  </binding>

  <service name="Hl7SoapServerService">
    <port name="Hl7SoapServerPort" binding="tns:Hl7SoapServerBinding">
      <soap:address location="{base_url}"/>
    </port>
  </service>

</definitions>
"""


def _escape_attribute_value(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def build_wsdl_document(base_url: str) -> bytes:
    """Auto-generate the WSDL for hl7_soap_server, addressed at ``base_url``.

    Args:
        base_url: The externally visible SOAP endpoint URL for the current
            request (scheme + host + endpoint path), so the generated
            ``soap:address`` always matches the environment that served
            the request (e.g. https://<env>-lims-hl7soapserver-ca.../soap).

    Returns:
        The WSDL document as UTF-8 encoded XML bytes.
    """
    wsdl_text = _WSDL_TEMPLATE.format(base_url=_escape_attribute_value(base_url))
    return wsdl_text.encode("utf-8")

