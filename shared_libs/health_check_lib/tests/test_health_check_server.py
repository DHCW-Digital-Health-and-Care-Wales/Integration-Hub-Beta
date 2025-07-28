import unittest
import socket
from unittest.mock import MagicMock

from health_check_lib.health_check_server import TCPHealthCheckServer


class TestTCPHealthCheckServer(unittest.TestCase):
    def setUp(self):
        # Use an ephemeral port (0) so the OS assigns an available one
        self.server = TCPHealthCheckServer(host='127.0.0.1', port=0)
        self.server.start()

        self.actual_port = self.server._server_socket.getsockname()[1]

    def tearDown(self):
        self.server.stop()

    def test_server_accepts_connection(self):
        try:
            with socket.create_connection(("127.0.0.1", self.actual_port), timeout=1) as sock:
                self.assertIsNotNone(sock)
        except Exception as e:
            self.fail(f"Could not connect to server: {e}")

    def test_server_stops_cleanly(self):
        self.server.stop()

        with self.assertRaises(ConnectionRefusedError):
            # Try to connect after server has stopped
            socket.create_connection(("127.0.0.1", self.actual_port), timeout=1)

    def test_default_parameters_constructor(self):
        server = TCPHealthCheckServer()

        self.assertEqual(server.host, "127.0.0.1")
        self.assertEqual(server.port, 9000)

    def test_custom_parameters_constructor(self):
        host = "localhost"
        port = 9876
        server = TCPHealthCheckServer(host=host, port=port)

        self.assertEqual(server.host, host)
        self.assertEqual(server.port, port)

    def test_exit_server_socket_closed(self):
        # Arrange
        exc_type = ValueError
        exc_value = ValueError("test error")
        exc_traceback = None
        self.server._server_socket.close()
        self.server._server_socket = MagicMock()

        # Act
        self.server.__exit__(exc_type, exc_value, exc_traceback)

        # Assert
        self.server._server_socket.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
