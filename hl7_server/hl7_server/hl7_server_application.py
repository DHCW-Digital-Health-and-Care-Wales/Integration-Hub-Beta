import logging
import os
import signal
import threading
from typing import Any

from hl7apy.mllp import MLLPServer

from .error_handler import ErrorHandler
from .generic_handler import GenericHandler

# Configure logging
log_level_str = os.environ.get("LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, log_level_str, logging.INFO)
logging.basicConfig(level=log_level, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class Hl7ServerApplication:
    def __init__(self) -> None:
        self._server_thread = None
        self.HOST = os.environ.get("HOST", "127.0.0.1")
        self.PORT = int(os.environ.get("PORT", "2575"))

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        self._server: MLLPServer = None

    def _signal_handler(self, signum: Any, frame: Any) -> None:
        logger.info("Shutdown signal received (signal %s).", signum)
        self.stop_server()

    def start_server(self) -> None:
        handlers = {"ADT^A31^ADT_A05": (GenericHandler,), "ADT^A28^ADT_A05": (GenericHandler,),
                    'ERR': (ErrorHandler,)}

        try:
            self._server = MLLPServer(self.HOST, self.PORT, handlers)
            self._server_thread = threading.Thread(target=self._server.serve_forever)
            self._server_thread.start()
            logger.info(f"MLLP Server listening on {self.HOST}:{self.PORT}")
        except Exception as e:
            logger.exception("Server encountered an unexpected error: %s", e)

    def stop_server(self) -> None:
        if self._server:
            logger.info("Shutting down the server...")
            self._server.shutdown()
            self._server.server_close()
            self._server_thread.join()
            logger.info("HL7 MLLP server shut down.")
