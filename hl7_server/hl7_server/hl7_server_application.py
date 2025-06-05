import logging
import os
import signal
import socket
from typing import Any

from hl7apy.mllp import MLLPServer

from .generic_handler import GenericHandler

# Configure logging
log_level_str = os.environ.get("LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, log_level_str, logging.INFO)
logging.basicConfig(level=log_level, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class Hl7ServerApplication:
    def __init__(self) -> None:
        self.HOST = os.environ.get("HOST", "127.0.0.1")
        self.PORT = int(os.environ.get("PORT", "2575"))

        self.terminated = False
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        self._server: MLLPServer = None

    def _signal_handler(self, signum: Any, frame: Any) -> None:
        logger.info("Shutdown signal received (signal %s).", signum)
        self.terminated = True
        if self._server:
            self._server.shutdown()

    def start_server(self) -> None:
        logger.info(f"MLLP Server listening on {self.HOST}:{self.PORT}")
        handlers = {"ADT^A31^ADT_A05": (GenericHandler,), "ADT^A28^ADT_A05": (GenericHandler,)}

        try:
            self._server = MLLPServer(self.HOST, self.PORT, handlers)
            self._server.socket.settimeout(10.0)  # Short timeout for graceful shutdown checking

            # Main server loop
            while not self.terminated:
                try:
                    self._server.serve_forever()
                except socket.timeout:
                    continue  # Loop back to check if `self.terminated` is True
                except Exception as e:
                    logger.exception("Server encountered an unexpected error: %s", e)
                    break
        finally:
            if self._server:
                self._server.server_close()
            logger.info("HL7 MLLP server shut down.")
