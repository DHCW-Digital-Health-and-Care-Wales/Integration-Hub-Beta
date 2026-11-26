from __future__ import annotations

import errno
import logging
import socket
import threading
import time
from types import TracebackType

logger = logging.getLogger(__name__)

_FATAL_ACCEPT_ERRNOS = frozenset({errno.EBADF, errno.EINVAL})
_RESOURCE_EXHAUSTION_ERRNOS = frozenset({errno.EMFILE, errno.ENFILE})
_DEFAULT_BACKLOG = 16


class TCPHealthCheckServer:
    """Lightweight TCP listener used by Azure Container Apps health probes."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        backlog: int = _DEFAULT_BACKLOG,
    ) -> None:
        self.host: str = host.strip() if host is not None and host.strip() else "127.0.0.1"
        self.port: int = port if port is not None else 9000
        self.backlog: int = max(1, backlog)
        self._server_socket: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._running: bool = False
        self._lock = threading.RLock()

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def bound_port(self) -> int | None:
        sock = self._server_socket
        if sock is None:
            return None
        try:
            return int(sock.getsockname()[1])
        except OSError:
            return None

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                server_socket.bind((self.host, self.port))
                server_socket.listen(self.backlog)
            except Exception:
                server_socket.close()
                raise

            self._server_socket = server_socket
            self._running = True
            self._thread = threading.Thread(
                target=self._run,
                args=(server_socket,),
                name="tcp-health-check",
                daemon=True,
            )
            self._thread.start()
            logger.info("Health check server listening on %s:%s", self.host, self.bound_port)

    def _run(self, server_socket: socket.socket) -> None:
        while self._running:
            try:
                client_socket, _ = server_socket.accept()
            except OSError as exc:
                if not self._running or exc.errno in _FATAL_ACCEPT_ERRNOS:
                    break
                logger.warning("Transient error accepting health probe connection: %s", exc)
                if exc.errno in _RESOURCE_EXHAUSTION_ERRNOS:
                    time.sleep(0.1)
                continue

            try:
                client_socket.close()
            except OSError:
                pass

    def mark_unhealthy(self, reason: str | None = None) -> None:
        """Stop accepting TCP probe connections so the orchestrator marks this container unhealthy."""
        if reason:
            logger.error("Marking health check server unhealthy: %s", reason)
        else:
            logger.error("Marking health check server unhealthy")
        self.stop()

    def stop(self) -> None:
        with self._lock:
            self._running = False
            server_socket = self._server_socket
            self._server_socket = None
            thread = self._thread
            self._thread = None

        if server_socket is not None:
            try:
                try:
                    server_socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                server_socket.close()
            except Exception as e:
                logger.warning("Failed to close socket: %s", e)
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1)

    def __enter__(self) -> TCPHealthCheckServer:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None,
    ) -> None:
        self.stop()
        logger.debug("Health check server closed.")
