import unittest
import socket

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


if __name__ == '__main__':
    unittest.main()
