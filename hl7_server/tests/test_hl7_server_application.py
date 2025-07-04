import os
import signal
import unittest
from threading import Thread
from typing import Any
from unittest.mock import MagicMock, patch

from hl7apy.mllp import MLLPServer

from hl7_server.hl7_server_application import Hl7ServerApplication

ENV_VARS = {
    "HOST": "127.0.0.1",
    "PORT": "2576",
    "EGRESS_QUEUE_NAME": "egress_queue",
    "SERVICE_BUS_CONNECTION_STRING": "Endpoint=sb://localhost",
    "AUDIT_QUEUE_NAME": "audit_queue",
    "WORKFLOW_ID": "test-workflow",
    "MICROSERVICE_ID": "test-service",
}


@patch.dict(os.environ, ENV_VARS)
@patch("hl7_server.hl7_server_application.MLLPServer")
@patch("hl7_server.hl7_server_application.ServiceBusClientFactory")
@patch("hl7_server.hl7_server_application.threading.Thread")
class TestHl7ServerApplication(unittest.TestCase):
    def setUp(self) -> None:
        self.app = Hl7ServerApplication()

    def _setup_mocks(self, mock_thread: Thread, mock_mllp_server: MLLPServer) -> tuple[MagicMock, MagicMock]:
        mock_server_instance = MagicMock()
        mock_thread_instance = MagicMock()
        mock_mllp_server.return_value = mock_server_instance
        mock_thread.return_value = mock_thread_instance  # type: ignore
        return mock_server_instance, mock_thread_instance

    def _assert_shutdown(self, server: MagicMock, thread: MagicMock) -> None:
        server.shutdown.assert_called_once()
        server.server_close.assert_called_once()
        thread.join.assert_called_once()

    def test_server_initialization_and_shutdown(
        self, mock_thread: Thread, _: Any, mock_mllp_server: MLLPServer
    ) -> None:
        server, thread = self._setup_mocks(mock_thread, mock_mllp_server)
        self.app.start_server()
        self.app.stop_server()

        self._assert_shutdown(server, thread)

    def test_signal_handler_shutdown(self, mock_thread: Thread, _: Any, mock_mllp_server: MLLPServer) -> None:
        server, thread = self._setup_mocks(mock_thread, mock_mllp_server)
        self.app.start_server()
        self.app._signal_handler(signal.SIGINT, None)

        self._assert_shutdown(server, thread)

    def test_server_exception_handling(self, mock_thread: Thread, _: Any, mock_mllp_server: MLLPServer) -> None:
        server, thread = self._setup_mocks(mock_thread, mock_mllp_server)
        thread.start.side_effect = RuntimeError("Simulated server error")

        with self.assertRaises(RuntimeError):
            self.app.start_server()

        self._assert_shutdown(server, thread)
