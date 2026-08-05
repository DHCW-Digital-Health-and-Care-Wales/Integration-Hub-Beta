"""Auto-generated WSDL document support for hl7_soap_server.

This module describes the hl7_soap_server SOAP contract using Spyne purely so
that an accurate, always up-to-date WSDL document can be generated on demand
(``GET /soap?wsdl``), addressed at whatever host served the request. This
means the generated ``soap:address`` is always correct for the environment
the server is running in (dev/load/prod), with no manual editing required.

IMPORTANT: The operations declared below are for WSDL introspection only.
Spyne never actually invokes them - all real request handling, SOAP envelope
unwrapping, schema validation, business validation, and downstream forwarding
continues to be performed by SoapMessageProcessor (see soap_processor.py),
completely unchanged. This keeps the auto-generated WSDL capability fully
decoupled from - and zero risk to - the existing, tested message processing
behaviour.
"""

from __future__ import annotations

from spyne import AnyXml, Application, ServiceBase, rpc
from spyne.interface.wsdl.wsdl11 import Wsdl11
from spyne.protocol.soap import Soap11

HL7_NAMESPACE = "urn:hl7-org:v2xml"
SERVICE_NAMESPACE = "urn:inthub:hl7-soap-server"


class Hl7SoapService(ServiceBase):
    """Describes the SOAP operations supported by hl7_soap_server for WSDL generation.

    Bodies are declared as ``AnyXml`` (document/literal *bare* style) because the
    real HL7 2.5 structure validation is performed by SoapMessageProcessor against
    the agreed XSD schemas (shared_libs/hl7_validation), not by Spyne itself.
    """

    @rpc(
        AnyXml(sub_ns=HL7_NAMESPACE, sub_name="ADT_A05"),
        _body_style="bare",
        _returns=AnyXml(sub_ns=SERVICE_NAMESPACE, sub_name="AckResponse"),
        _in_message_name="SubmitADT_A05Request",
        _out_message_name="SubmitHL7MessageResponse",
    )
    def SubmitADT_A05(ctx, payload):  # noqa: N802, N805 - SOAP operation name / spyne convention
        raise NotImplementedError("hl7_soap_server handles requests via SoapMessageProcessor, not Spyne.")

    @rpc(
        AnyXml(sub_ns=HL7_NAMESPACE, sub_name="ADT_A39"),
        _body_style="bare",
        _returns=AnyXml(sub_ns=SERVICE_NAMESPACE, sub_name="AckResponse"),
        _in_message_name="SubmitADT_A39Request",
        _out_message_name="SubmitHL7MessageResponse",
    )
    def SubmitADT_A39(ctx, payload):  # noqa: N802, N805 - SOAP operation name / spyne convention
        raise NotImplementedError("hl7_soap_server handles requests via SoapMessageProcessor, not Spyne.")


_soap_application = Application(
    [Hl7SoapService],
    tns=SERVICE_NAMESPACE,
    name="Hl7SoapServer",
    in_protocol=Soap11(validator=None),
    out_protocol=Soap11(),
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
    interface_document = Wsdl11(_soap_application.interface)
    interface_document.build_interface_document(base_url)
    return interface_document.get_interface_document()
