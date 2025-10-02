import logging
import os
import signal
import threading
from typing import Any

from hl7apy.mllp import MLLPRequestHandler, MLLPServer
from message_bus_lib.connection_config import ConnectionConfig
from message_bus_lib.servicebus_client_factory import ServiceBusClientFactory

from .app_config import AppConfig
from .generic_handler import GenericHandler

log_level_str = os.environ.get("LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, log_level_str, logging.INFO)
logging.basicConfig(level=log_level, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class CustomMLLPRequestHandler(MLLPRequestHandler):

    def _route_message(self, msg):

        try:
            generic_handler_config = self.handlers.get('generic')
            if not generic_handler_config:
                raise ValueError("Generic handler configuration not found in handlers")

            handler_class, *handler_args = generic_handler_config

            handler = self._create_handler(handler_class, msg, handler_args)

            return handler.reply()
        except Exception as e:
            logger.error("Error routing message: %s", e)
            try:
                err_handler, args = self.handlers['ERR'][0], self.handlers['ERR'][1:]
                h = self._create_error_handler(err_handler, e, msg, args)
                return h.reply()
            except KeyError:
                raise e


class Hl7MockReceiver:
    def __init__(self) -> None:
        self.sender_client = None
        self._server_thread: threading.Thread
        self.HOST = os.environ.get("HOST", "127.0.0.1")
        self.PORT = int(os.environ.get("PORT", "2576"))

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        self._server: MLLPServer = None

    def _signal_handler(self, signum: Any, frame: Any) -> None:
        logger.info("Shutdown signal received (signal %s).", signum)
        self.stop_server()

    def start_server(self) -> None:
        app_config = AppConfig.read_env_config()
        client_config = ConnectionConfig(app_config.connection_string, app_config.service_bus_namespace)
        factory = ServiceBusClientFactory(client_config)

        self.sender_client = factory.create_queue_sender_client(app_config.egress_queue_name)

        handlers = {
            'generic': (GenericHandler, self.sender_client),
        }

        try:
            self._server = MLLPServer(
                self.HOST,
                self.PORT,
                handlers,
                request_handler_class=CustomMLLPRequestHandler
            )
            self._server_thread = threading.Thread(target=self._server.serve_forever)
            self._server_thread.start()
            logger.info(f"MLLP Server listening on {self.HOST}:{self.PORT} (accepting all message types)")
        except Exception as e:
            logger.exception("Server encountered an unexpected error: %s", e)
            self.stop_server()
            raise

    def stop_server(self) -> None:
        logger.info("Shutting down the server...")

        if self.sender_client:
            self.sender_client.close()
            logger.info("Service Bus sender client shut down.")

        if self._server:
            self._server.shutdown()
            self._server.server_close()
            logger.info("HL7 MLLP server shut down.")

        if self._server_thread:
            self._server_thread.join()
