import errno
import socket
import threading
import unittest
from unittest.mock import MagicMock

from health_check_lib.health_check_server import TCPHealthCheckServer


class TestTCPHealthCheckServer(unittest.TestCase):
    def setUp(self) -> None:
        # Use an ephemeral port (0) so the OS assigns an available one
        self.server = TCPHealthCheckServer(host="127.0.0.1", port=0)
        self.server.start()

        assert self.server.bound_port is not None
        self.actual_port = self.server.bound_port

    def tearDown(self) -> None:
        self.server.stop()

    def test_server_accepts_connection(self) -> None:
        try:
            with socket.create_connection(("127.0.0.1", self.actual_port), timeout=1) as sock:
                self.assertIsNotNone(sock)
        except Exception as e:
            self.fail(f"Could not connect to server: {e}")

    def test_server_accepts_concurrent_connections(self) -> None:
        errors: list[Exception] = []

        def connect() -> None:
            try:
                with socket.create_connection(("127.0.0.1", self.actual_port), timeout=2):
                    pass
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=connect) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=3)

        self.assertEqual(errors, [])

    def test_server_stops_cleanly(self) -> None:
        self.server.stop()

        with self.assertRaises(ConnectionRefusedError):
            socket.create_connection(("127.0.0.1", self.actual_port), timeout=1)

    def test_mark_unhealthy_closes_probe_port(self) -> None:
        self.server.mark_unhealthy("fatal Service Bus auth failure")

        self.assertFalse(self.server.is_running)
        with self.assertRaises(ConnectionRefusedError):
            socket.create_connection(("127.0.0.1", self.actual_port), timeout=1)

    def test_start_is_idempotent(self) -> None:
        original_socket = self.server._server_socket
        original_thread = self.server._thread

        self.server.start()

        self.assertIs(self.server._server_socket, original_socket)
        self.assertIs(self.server._thread, original_thread)

    def test_stop_is_idempotent(self) -> None:
        self.server.stop()
        self.server.stop()
        self.assertFalse(self.server.is_running)

    def test_default_parameters_constructor(self) -> None:
        server = TCPHealthCheckServer()

        self.assertEqual(server.host, "127.0.0.1")
        self.assertEqual(server.port, 9000)

    def test_blank_host_falls_back_to_loopback(self) -> None:
        server = TCPHealthCheckServer(host="   ", port=None)

        self.assertEqual(server.host, "127.0.0.1")
        self.assertEqual(server.port, 9000)

    def test_custom_parameters_constructor(self) -> None:
        host = "localhost"
        port = 9876
        server = TCPHealthCheckServer(host=host, port=port)

        self.assertEqual(server.host, host)
        self.assertEqual(server.port, port)

    def test_exit_server_socket_closed(self) -> None:
        exc_type = ValueError
        exc_value = ValueError("test error")
        exc_traceback = None
        assert self.server._server_socket is not None
        self.server._server_socket.close()
        mock_socket = MagicMock()
        self.server._server_socket = mock_socket

        self.server.__exit__(exc_type, exc_value, exc_traceback)

        mock_socket.close.assert_called_once()

    def test_socket_binding_with_port_conflict(self) -> None:
        server1 = TCPHealthCheckServer(host="127.0.0.1", port=0)
        server1.start()

        assigned_port = server1.bound_port

        server2 = TCPHealthCheckServer(host="127.0.0.1", port=0)
        server2.start()

        port2 = server2.bound_port
        self.assertNotEqual(assigned_port, port2)

        self.assertTrue(server1.is_running)
        self.assertTrue(server2.is_running)

        server1.stop()
        server2.stop()

    def test_shutdown_with_socket_shutdown_error(self) -> None:
        mock_socket = MagicMock()
        mock_socket.shutdown.side_effect = OSError("Socket shutdown error")
        mock_socket.close.return_value = None

        server = TCPHealthCheckServer(host="127.0.0.1", port=0)
        server._server_socket = mock_socket
        server._thread = None

        try:
            server.stop()
        except Exception as e:
            self.fail(f"Server stop should handle socket shutdown errors gracefully: {e}")

    def test_transient_accept_oserror_does_not_kill_loop(self) -> None:
        server = TCPHealthCheckServer(host="127.0.0.1", port=0)
        server._running = True

        client_sock = MagicMock()
        mock_server_sock = MagicMock()
        calls = 0

        def accept_side_effect() -> tuple[MagicMock, tuple[str, int]]:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError(errno.ECONNABORTED, "Software caused connection abort")
            if calls == 2:
                return client_sock, ("127.0.0.1", 55555)
            server._running = False
            raise OSError(errno.EBADF, "Bad file descriptor")

        mock_server_sock.accept.side_effect = accept_side_effect

        server._run(mock_server_sock)

        self.assertEqual(calls, 3)
        client_sock.close.assert_called_once()

    def test_fatal_ebadf_exits_accept_loop(self) -> None:
        server = TCPHealthCheckServer(host="127.0.0.1", port=0)
        server._running = True

        mock_server_sock = MagicMock()
        mock_server_sock.accept.side_effect = OSError(errno.EBADF, "Bad file descriptor")

        server._run(mock_server_sock)

        mock_server_sock.accept.assert_called_once()


if __name__ == "__main__":
    unittest.main()
