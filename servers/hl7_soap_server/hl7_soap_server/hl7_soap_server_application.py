from __future__ import annotations

import logging
import os
import signal
import ssl
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, cast
from urllib.parse import parse_qsl, urlsplit

from event_logger_lib.event_logger import EventLogger
from health_check_lib.health_check_server import TCPHealthCheckServer
from message_bus_lib.connection_config import ConnectionConfig
from message_bus_lib.message_sender_client import MessageSenderClient
from message_bus_lib.message_store_client import MessageStoreClient
from message_bus_lib.servicebus_client_factory import ServiceBusClientFactory
from metric_sender_lib.metric_sender import MetricSender

from .app_config import AppConfig
from .soap_processor import SoapMessageProcessor, build_soap_fault_response
from .wsdl_service import build_wsdl_document

log_level_str = os.environ.get("LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, log_level_str, logging.INFO)
logging.basicConfig(level=log_level, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

azure_log_level_str = os.environ.get("AZURE_LOG_LEVEL", "WARN").upper()
azure_log_level = getattr(logging, azure_log_level_str, logging.WARN)
logging.getLogger("azure").setLevel(azure_log_level)


class Hl7SoapServerApplication:
    def __init__(self) -> None:
        self.sender_client: MessageSenderClient = None
        self.message_store_client: MessageStoreClient = None
        self.event_logger: EventLogger = None
        self.metric_sender: MetricSender = None
        self.health_check_server: TCPHealthCheckServer = None
        self._server: HTTPServer | None = None
        self._server_thread: threading.Thread | None = None

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum: Any, frame: Any) -> None:
        logger.info("Shutdown signal received (signal %s).", signum)
        self.stop_server()

    def start_server(self) -> None:
        app_config = AppConfig.read_env_config()

        client_config = ConnectionConfig(app_config.connection_string, app_config.service_bus_namespace)
        factory = ServiceBusClientFactory(client_config)

        if app_config.egress_topic_name:
            self.sender_client = factory.create_topic_sender_client(
                app_config.egress_topic_name, app_config.egress_session_id
            )
            logger.info("Configured to send messages to topic: %s", app_config.egress_topic_name)
        elif app_config.egress_queue_name:
            self.sender_client = factory.create_queue_sender_client(
                app_config.egress_queue_name, app_config.egress_session_id
            )
            logger.info("Configured to send messages to queue: %s", app_config.egress_queue_name)

        self.message_store_client = factory.create_message_store_client(
            app_config.message_store_queue_name, app_config.microservice_id, app_config.peer_service
        )

        self.event_logger = EventLogger(app_config.workflow_id, app_config.microservice_id)
        self.metric_sender = MetricSender(
            app_config.workflow_id,
            app_config.microservice_id,
            app_config.health_board,
            app_config.peer_service,
        )
        self.health_check_server = TCPHealthCheckServer(app_config.health_check_hostname, app_config.health_check_port)

        processor = SoapMessageProcessor(
            sender_client=self.sender_client,
            event_logger=self.event_logger,
            metric_sender=self.metric_sender,
            message_store_client=self.message_store_client,
            workflow_id=app_config.workflow_id,
            egress_session_id=app_config.egress_session_id,
            schema_group=app_config.schema_group,
            allowed_hl7_structures=app_config.allowed_hl7_structures,
            allowed_assigning_authorities=app_config.allowed_assigning_authorities,
        )

        handler_class = create_soap_request_handler(
            processor=processor,
            endpoint_path=app_config.soap_endpoint_path,
            max_request_size_bytes=app_config.max_request_size_bytes,
            tls_enabled=bool(app_config.tls_cert_file and app_config.tls_key_file),
        )

        try:
            self._server = HTTPServer((app_config.host, app_config.port), handler_class)
            if app_config.tls_cert_file and app_config.tls_key_file:
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                context.load_cert_chain(certfile=app_config.tls_cert_file, keyfile=app_config.tls_key_file)
                self._server.socket = context.wrap_socket(self._server.socket, server_side=True)
                logger.info("SOAP server TLS enabled using configured certificate and key files")

            self._server_thread = threading.Thread(target=self._server.serve_forever)
            self._server_thread.start()
            self.health_check_server.start()

            logger.info(
                "SOAP server listening on %s:%s%s (max request size: %s bytes)",
                app_config.host,
                app_config.port,
                app_config.soap_endpoint_path,
                app_config.max_request_size_bytes,
            )
        except Exception:
            logger.exception("SOAP server encountered an unexpected startup error")
            self.stop_server()
            raise

    def stop_server(self) -> None:
        logger.info("Shutting down SOAP server...")

        if self.sender_client:
            self.sender_client.close()
            logger.info("Service Bus sender client shut down.")

        if self.message_store_client:
            self.message_store_client.close()
            logger.info("Message store client shut down.")

        if self.health_check_server:
            self.health_check_server.stop()
            logger.info("Health check server shut down.")

        if self._server:
            self._server.shutdown()
            self._server.server_close()
            logger.info("SOAP HTTP server shut down.")

        if self._server_thread:
            self._server_thread.join()

        logger.info("SOAP server shutdown complete.")


def create_soap_request_handler(
    processor: SoapMessageProcessor,
    endpoint_path: str,
    max_request_size_bytes: int,
    tls_enabled: bool = False,
) -> type[BaseHTTPRequestHandler]:
    class SoapRequestHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
            if self.path != endpoint_path:
                self._write_response(404, build_soap_fault_response("Client", "Unknown SOAP endpoint path."))
                return

            content_length_header = self.headers.get("Content-Length")
            if not content_length_header:
                self._write_response(411, build_soap_fault_response("Client", "Content-Length header is required."))
                return

            try:
                content_length = int(content_length_header)
            except ValueError:
                self._write_response(400, build_soap_fault_response("Client", "Invalid Content-Length header."))
                return

            if content_length <= 0:
                self._write_response(400, build_soap_fault_response("Client", "SOAP request body is empty."))
                return

            if content_length > max_request_size_bytes:
                self._write_response(
                    413,
                    build_soap_fault_response(
                        "Client",
                        (
                            f"SOAP request body exceeds configured limit of {max_request_size_bytes} bytes. "
                            f"Received: {content_length} bytes."
                        ),
                    ),
                )
                return

            try:
                request_body = self.rfile.read(content_length).decode("utf-8", errors="strict")
            except UnicodeDecodeError:
                self._write_response(
                    400,
                    build_soap_fault_response("Client", "SOAP request body must be UTF-8 encoded."),
                )
                return
            status_code, response_xml = processor.process(request_body)
            self._write_response(status_code, response_xml)

        def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
            # Some reverse proxies (including Azure Container Apps ingress in
            # certain configurations) forward requests using an absolute-form
            # request-target (e.g. "https://host/soap?wsdl") rather than the
            # relative-form ("/soap?wsdl"). urlsplit() correctly extracts just
            # the path/query in either case, whereas a raw partition("?") on
            # self.path would leave a scheme+host prefix on request_path and
            # never match endpoint_path.
            parsed_path = urlsplit(self.path)
            if parsed_path.path == endpoint_path and self._is_wsdl_query(parsed_path.query):
                self._write_wsdl_response()
                return
            self._write_response(405, build_soap_fault_response("Client", "SOAP endpoint accepts POST only."))

        @staticmethod
        def _is_wsdl_query(query: str) -> bool:
            # Different SOAP client tooling requests the WSDL in slightly
            # different forms - e.g. a bare "?wsdl" (SoapUI, most manual
            # requests), "?wsdl=" or "?wsdl=true" (clients/proxies that always
            # serialise query parameters as key=value pairs), or "?WSDL" with
            # different casing. Matching only the exact string "wsdl" (as a
            # previous version of this check did) rejects all of those valid
            # variants and causes the client to receive the 405 SOAP-fault
            # response instead of the WSDL document, which then fails to
            # parse as WSDL. Checking for a "wsdl" key (case-insensitive,
            # value ignored) covers all of these forms.
            query_keys = {key.lower() for key, _ in parse_qsl(query, keep_blank_values=True)}
            return "wsdl" in query_keys

        def _write_wsdl_response(self) -> None:
            scheme = self._determine_scheme()
            server_address = cast("tuple[str, int]", self.server.server_address)
            host = self.headers.get("Host") or f"{server_address[0]}:{server_address[1]}"
            base_url = f"{scheme}://{host}{endpoint_path}"
            try:
                wsdl_bytes = build_wsdl_document(base_url)
            except Exception:
                logger.exception("Failed to auto-generate WSDL document")
                self._write_response(
                    500, build_soap_fault_response("Server", "Unable to generate WSDL document.")
                )
                return

            self.send_response(200)
            self.send_header("Content-Type", "text/xml; charset=utf-8")
            self.send_header("Content-Length", str(len(wsdl_bytes)))
            # Some browsers/proxies heuristically cache GET responses (including
            # error responses such as 405) when no explicit caching headers are
            # present. Without this, a client that hit this exact URL once
            # before the WSDL feature existed (or during a bad deployment)
            # could keep re-serving that stale cached response indefinitely,
            # never re-contacting the now-fixed server.
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(wsdl_bytes)

        def _determine_scheme(self) -> str:
            forwarded_proto = self.headers.get("X-Forwarded-Proto")
            if forwarded_proto:
                return forwarded_proto.split(",")[0].strip()
            return "https" if tls_enabled else "http"

        def log_message(self, message_format: str, *args: object) -> None:
            logger.info("SOAP request: %s", message_format % args)

        def _write_response(self, status_code: int, xml_content: str) -> None:
            encoded = xml_content.encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "text/xml; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            # 405 (and other error statuses) are heuristically cacheable per
            # RFC 7231 SS6.1 when no explicit caching headers are sent, so a
            # client could otherwise keep re-serving a stale cached fault
            # response even after the server-side issue is fixed.
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(encoded)

    return SoapRequestHandler
