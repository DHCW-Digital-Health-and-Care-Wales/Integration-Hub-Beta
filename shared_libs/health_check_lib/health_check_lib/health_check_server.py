import socket
import threading
import logging

class TCPHealthCheckServer:
    def __init__(self, host='127.0.0.1', port=9000):
        self.host = host
        self.port = port
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
                logging.warning(f"Failed to close socket: {e}")
