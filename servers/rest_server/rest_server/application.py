"""FastAPI app module - imported by uvicorn as ``rest_server.application:app``.

Run via ``python -m rest_server`` (see ``__main__.py``), which starts uvicorn against this app.
"""
from otel_lib import configure_otel

from rest_server.rest_server_application import RestServerApplication

configure_otel("rest-server")
app = RestServerApplication().build_app()
