import os
import signal
import socket
import unittest
from unittest.mock import MagicMock, patch

from hl7_server.hl7server.hl7_server_application import Hl7ServerApplication


class TestHl7ServerApplication(unittest.TestCase):

    @patch.dict(os.environ, {"HOST": "127.0.0.1", "PORT": "2576"})
    @patch("hl7_server.hl7server.hl7_server_application.MLLPServer")
    def test_server_initialization_and_shutdown(self, mock_mllp_server):
        mock_server_instance = MagicMock()
        mock_mllp_server.return_value = mock_server_instance


        # Simulate a timeout to exit serve_forever loop
        mock_server_instance.serve_forever.side_effect = socket.timeout()

        app = Hl7ServerApplication()
        app.terminated = True  # Simulate shutdown trigger
        app.start_server()

        self.assertTrue(mock_server_instance.server_close.called)

    @patch.dict(os.environ, {"HOST": "127.0.0.1", "PORT": "2576"})
    @patch("hl7_server.hl7server.hl7_server_application.MLLPServer")
    def test_signal_handler_shutdown(self, mock_mllp_server):
        app = Hl7ServerApplication()
        mock_server_instance = MagicMock()
        app._server = mock_server_instance

        app._signal_handler(signal.SIGINT, None)

        self.assertTrue(app.terminated)
        mock_server_instance.shutdown.assert_called_once()

    @patch.dict(os.environ, {"HOST": "127.0.0.1", "PORT": "2576"})
    @patch("hl7_server.hl7server.hl7_server_application.MLLPServer")
    def test_server_exception_handling(self, mock_mllp_server):
        mock_server_instance = MagicMock()
        mock_server_instance.serve_forever.side_effect = Exception("Test exception")
        mock_mllp_server.return_value = mock_server_instance

        app = Hl7ServerApplication()
        app.terminated = False

        # Run the server and catch the exception to prevent crash
        app.start_server()

        self.assertTrue(mock_server_instance.server_close.called)

