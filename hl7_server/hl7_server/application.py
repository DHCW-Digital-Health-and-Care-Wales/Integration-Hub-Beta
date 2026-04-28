from hl7_server.hl7_server_application import Hl7ServerApplication

app = Hl7ServerApplication()
# TODO: add configure_otel() call once otel_lib is validated
app.start_server()
