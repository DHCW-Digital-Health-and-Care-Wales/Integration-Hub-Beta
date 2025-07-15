import socket
import threading
import logging

logger = logging.getLogger(__name__)

class TCPHealthCheckServer:
    def __init__(self, host: str | None = None, port: int | None = None):
        self.host = host or "127.0.0.1"
        self.port = port or 9000
        self._server_socket = None
        self._thread = None
        self._running = False

    def start(self):
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind((self.host, self.port))
        self._server_socket.listen(1)
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while self._running:
            try:
                client_socket, _ = self._server_socket.accept()
                client_socket.close()
            except OSError:
                break

    def stop(self):
        self._running = False
        if self._server_socket:
            try:
                self._server_socket.close()
            except Exception as e:
                logger.warning(f"Failed to close socket: {e}")

    def __enter__(self):
        return self

    def __exit__(self):
        self.stop()
        logger.debug("Health check server closed.")
