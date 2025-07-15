import logging
import os
import signal
import threading
from typing import Any

from health_check_lib.health_check_server import TCPHealthCheckServer
from hl7apy.mllp import MLLPServer
from message_bus_lib.audit_service_client import AuditServiceClient
from message_bus_lib.connection_config import ConnectionConfig
from message_bus_lib.message_sender_client import MessageSenderClient
from message_bus_lib.servicebus_client_factory import ServiceBusClientFactory

from hl7_server.hl7_validator import HL7Validator

from .app_config import AppConfig
from .error_handler import ErrorHandler
from .generic_handler import GenericHandler

# Configure logging
log_level_str = os.environ.get("LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, log_level_str, logging.INFO)
logging.basicConfig(level=log_level, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class Hl7ServerApplication:
    def __init__(self) -> None:
        self.sender_client: MessageSenderClient = None
        self.audit_client: AuditServiceClient = None
        self._server_thread: threading.Thread | None = None
        self.health_check_server: TCPHealthCheckServer = None
        self.HOST = os.environ.get("HOST", "127.0.0.1")
        self.PORT = int(os.environ.get("PORT", "2575"))

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        self._server: MLLPServer | None = None

    def _signal_handler(self, signum: Any, frame: Any) -> None:
        logger.info("Shutdown signal received (signal %s).", signum)
        self.stop_server()

    def start_server(self) -> None:
        app_config = AppConfig.read_env_config()
        client_config = ConnectionConfig(app_config.connection_string, app_config.service_bus_namespace)
        factory = ServiceBusClientFactory(client_config)

        self.sender_client = factory.create_queue_sender_client(app_config.egress_queue_name)
        audit_sender_client = factory.create_queue_sender_client(app_config.audit_queue_name)
        self.audit_client = AuditServiceClient(audit_sender_client, app_config.workflow_id, app_config.microservice_id)
        self.validator = HL7Validator(app_config.hl7_version, app_config.sending_app)
        self.health_check_server = TCPHealthCheckServer(app_config.health_check_hostname, app_config.health_check_port)

        handlers = {
            "ADT^A31^ADT_A05": (GenericHandler, self.sender_client, self.audit_client, self.validator),
            "ADT^A28^ADT_A05": (GenericHandler, self.sender_client, self.audit_client, self.validator),
            "ADT^A40^ADT_A05": (GenericHandler, self.sender_client, self.audit_client, self.validator),
            "ERR": (ErrorHandler, self.audit_client),
        }

        try:
            self._server = MLLPServer(self.HOST, self.PORT, handlers)
            self._server_thread = threading.Thread(target=self._server.serve_forever)
            self._server_thread.start()
            logger.info(f"MLLP Server listening on {self.HOST}:{self.PORT}")
            self.health_check_server.start()
        except Exception as e:
            logger.exception("Server encountered an unexpected error: %s", e)
            self.stop_server()
            raise

    def stop_server(self) -> None:
        logger.info("Shutting down the server...")

        if self.sender_client:
            self.sender_client.close()
            logger.info("Service Bus sender client shut down.")

        if self.audit_client:
            self.audit_client.close()
            logger.info("Audit service client shut down.")

        if self.health_check_server:
            self.health_check_server.stop()
            logger.info("Health check server shut down.")

        if self._server:
            self._server.shutdown()
            self._server.server_close()
            logger.info("HL7 MLLP server shut down.")

        if self._server_thread:
            self._server_thread.join()

        logger.info("Server shutdown complete.")
