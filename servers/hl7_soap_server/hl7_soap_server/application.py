from otel_lib import configure_otel

from hl7_soap_server.hl7_soap_server_application import Hl7SoapServerApplication

configure_otel("hl7-soap-server")
app = Hl7SoapServerApplication()
app.start_server()
