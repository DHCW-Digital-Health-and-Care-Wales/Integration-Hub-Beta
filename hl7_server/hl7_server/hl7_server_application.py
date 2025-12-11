import logging
import os
import signal
import threading
from typing import Any

from event_logger_lib.event_logger import EventLogger
from health_check_lib.health_check_server import TCPHealthCheckServer
from message_bus_lib.connection_config import ConnectionConfig
from message_bus_lib.message_sender_client import MessageSenderClient
from message_bus_lib.servicebus_client_factory import ServiceBusClientFactory
from metric_sender_lib.metric_sender import MetricSender

from hl7_server.hl7_validator import HL7Validator
from hl7_server.size_limited_mllp_server import SizeLimitedMLLPServer

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
        self.event_logger: EventLogger = None
        self.metric_sender: MetricSender = None
        self._server_thread: threading.Thread | None = None
        self.health_check_server: TCPHealthCheckServer = None
        self.HOST = os.environ.get("HOST", "127.0.0.1")
        self.PORT = int(os.environ.get("PORT", "2575"))

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        self._server: SizeLimitedMLLPServer | None = None

    def _signal_handler(self, signum: Any, frame: Any) -> None:
        logger.info("Shutdown signal received (signal %s).", signum)
        self.stop_server()

    def start_server(self) -> None:
        app_config = AppConfig.read_env_config()
        client_config = ConnectionConfig(app_config.connection_string, app_config.service_bus_namespace)
        factory = ServiceBusClientFactory(client_config)

        if app_config.egress_topic_name:
            self.sender_client = factory.create_topic_sender_client(app_config.egress_topic_name)
            logger.info(f"Configured to send messages to topic: {app_config.egress_topic_name}")
        else:
            self.sender_client = factory.create_queue_sender_client(
                app_config.egress_queue_name, app_config.egress_session_id
            )
            logger.info(f"Configured to send messages to queue: {app_config.egress_queue_name}")

        self.event_logger = EventLogger(app_config.workflow_id, app_config.microservice_id)
        logger.debug(f"EventLogger instantiated on hl7_server for workflow: {app_config.workflow_id}")

        self.metric_sender = MetricSender(
            app_config.workflow_id, app_config.microservice_id, app_config.health_board, app_config.peer_service
        )
        self.validator = HL7Validator(app_config.hl7_version, app_config.sending_app, app_config.hl7_validation_flow)
        self.health_check_server = TCPHealthCheckServer(app_config.health_check_hostname, app_config.health_check_port)

        flow_name = app_config.hl7_validation_flow

        generic_handler_args = (
            GenericHandler,
            self.sender_client,
            self.event_logger,
            self.metric_sender,
            self.validator,
            flow_name,
        )

        handlers = {
            "ADT^A31^ADT_A05": generic_handler_args,
            "ADT^A28^ADT_A05": generic_handler_args,
            # Paris A40 message
            "ADT^A40^ADT_A39": generic_handler_args,
            # Chemocare messages and MPI Outbound
            "ADT^A31": generic_handler_args,
            "ADT^A28": generic_handler_args,
            # TODO no examples provided for Chemocare A40, but assuming similar message type structure
            "ADT^A40": generic_handler_args,
            # PIMS messages
            "ADT^A04^ADT_A01": generic_handler_args,
            "ADT^A08^ADT_A01": generic_handler_args,
            "ADT^A40^ADT_A40": generic_handler_args,
            "ERR": (ErrorHandler, self.event_logger),
        }

        try:
            self._server = SizeLimitedMLLPServer(
                self.HOST, self.PORT, handlers, app_config.max_message_size_bytes, self.event_logger
            )
            self._server_thread = threading.Thread(target=self._server.serve_forever)
            self._server_thread.start()
            logger.info(
                f"MLLP Server listening on {self.HOST}:{self.PORT} "
                f"with message size limit: {app_config.max_message_size_bytes} bytes"
            )
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
