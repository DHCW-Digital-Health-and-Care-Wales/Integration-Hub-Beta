import socket
import signal
import logging
import os
from hl7apy.mllp import MLLPServer
from hl7_server.dhcw_nhs_wale.generic_handler import GenericHandler

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


class Hl7ServerApplication:

    def __init__(self):
        self.REMOTE_HOST = os.environ.get('REMOTE_HOST', '0.0.0.0')  # Default to all interfaces
        self.REMOTE_PORT = int(os.environ.get('REMOTE_PORT', 2575))  # Default HL7 MLLP port

        self.terminated = False
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        self._server = None

    def _signal_handler(self, signum, frame):
        logger.info("Shutdown signal received (signal %s).", signum)
        self.terminated = True
        if self._server:
            self._server.shutdown()


    def start_server(self) -> None:

        logger.info(f"MLLP Server listening on {self.REMOTE_HOST}:{self.REMOTE_PORT}")
        handlers = {"ADT^A31^ADT_A05": (GenericHandler,)}

        try:
            self._server = MLLPServer(self.REMOTE_HOST, self.REMOTE_PORT, handlers)
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


if __name__ == '__main__':
    app = Hl7ServerApplication()
    app.start_server()
