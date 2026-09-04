from otel_lib import configure_otel

from hl7_server.hl7_server_application import Hl7ServerApplication

configure_otel("hl7-server")
app = Hl7ServerApplication()
app.start_server()
