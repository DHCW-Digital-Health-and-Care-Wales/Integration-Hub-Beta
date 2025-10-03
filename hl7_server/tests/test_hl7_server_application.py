import os
import signal
import unittest
from typing import Dict
from unittest.mock import MagicMock, patch

from hl7apy.mllp import MLLPServer

from hl7_server.hl7_server_application import Hl7ServerApplication

ENV_VARS_QUEUE: Dict[str, str] = {
    "HOST": "127.0.0.1",
    "PORT": "2576",
    "EGRESS_QUEUE_NAME": "egress_queue",
    "SERVICE_BUS_CONNECTION_STRING": "Endpoint=sb://localhost",
    "AUDIT_QUEUE_NAME": "audit_queue",
    "WORKFLOW_ID": "test-workflow",
    "MICROSERVICE_ID": "test-service",
    "HEALTH_CHECK_HOST": "127.0.0.1",
    "HEALTH_CHECK_PORT": "9000",
}

ENV_VARS_TOPIC: Dict[str, str] = {
    "HOST": "127.0.0.1",
    "PORT": "2576",
    "EGRESS_TOPIC_NAME": "egress_topic",
    "SERVICE_BUS_CONNECTION_STRING": "Endpoint=sb://localhost",
    "AUDIT_QUEUE_NAME": "audit_queue",
    "WORKFLOW_ID": "test-workflow",
    "MICROSERVICE_ID": "test-service",
    "HEALTH_CHECK_HOST": "127.0.0.1",
    "HEALTH_CHECK_PORT": "9000",
}


@patch.dict(os.environ, ENV_VARS_QUEUE)
@patch("hl7_server.hl7_server_application.TCPHealthCheckServer")
@patch("hl7_server.hl7_server_application.MLLPServer")
@patch("hl7_server.hl7_server_application.ServiceBusClientFactory")
@patch("hl7_server.hl7_server_application.threading.Thread")
class TestHl7ServerApplicationQueue(unittest.TestCase):
    def setUp(self) -> None:
        self.app = Hl7ServerApplication()

    def _setup_mocks(self, mock_thread: MagicMock, mock_mllp_server: MLLPServer, mock_health_check: MagicMock) -> tuple[
        MagicMock, MagicMock, MagicMock]:
        mock_server_instance = MagicMock()
        mock_thread_instance = MagicMock()
        mock_health_instance = MagicMock()
        mock_mllp_server.return_value = mock_server_instance
        mock_thread.return_value = mock_thread_instance
        mock_health_check.return_value = mock_health_instance
        return mock_server_instance, mock_thread_instance, mock_health_instance

    def _assert_shutdown(self, server: MagicMock, thread: MagicMock, health_check: MagicMock) -> None:
        server.shutdown.assert_called_once()
        server.server_close.assert_called_once()
        thread.join.assert_called_once()
        health_check.stop.assert_called_once()

    def test_server_initialization_and_shutdown(self, mock_thread: MagicMock, mock_factory: MagicMock,
                                                mock_mllp_server: MLLPServer, mock_health_check: MagicMock) -> None:
        server, thread, health_check = self._setup_mocks(mock_thread, mock_mllp_server, mock_health_check)

        self.app.start_server()
        self.app.stop_server()

        self._assert_shutdown(server, thread, health_check)

    def test_signal_handler_shutdown(self, mock_thread: MagicMock, mock_factory: MagicMock,
                                     mock_mllp_server: MLLPServer, mock_health_check: MagicMock) -> None:
        server, thread, health_check = self._setup_mocks(mock_thread, mock_mllp_server, mock_health_check)

        self.app.start_server()
        self.app._signal_handler(signal.SIGINT, None)

        self._assert_shutdown(server, thread, health_check)

    def test_server_exception_handling(self, mock_thread: MagicMock, mock_factory: MagicMock,
                                       mock_mllp_server: MLLPServer,
                                       mock_health_check: MagicMock) -> None:
        server, thread, health_check = self._setup_mocks(mock_thread, mock_mllp_server, mock_health_check)
        thread.start.side_effect = RuntimeError("Simulated server error")

        with self.assertRaises(RuntimeError):
            self.app.start_server()

        self._assert_shutdown(server, thread, health_check)

    def test_health_check_initialization(self, mock_thread: MagicMock, mock_factory: MagicMock,
                                         mock_mllp_server: MLLPServer, mock_health_check: MagicMock) -> None:
        server, thread, health_check = self._setup_mocks(mock_thread, mock_mllp_server, mock_health_check)

        self.app.start_server()

        mock_health_check.assert_called_once_with("127.0.0.1", 9000)
        health_check.start.assert_called_once()

        self.app.stop_server()
        self._assert_shutdown(server, thread, health_check)

    def test_creates_queue_sender_client(self, mock_thread: MagicMock, mock_factory: MagicMock,
                                         mock_mllp_server: MLLPServer, mock_health_check: MagicMock) -> None:
        server, thread, health_check = self._setup_mocks(mock_thread, mock_mllp_server, mock_health_check)
        mock_factory_instance = mock_factory.return_value

        self.app.start_server()

        mock_factory_instance.create_queue_sender_client.assert_called_once_with("egress_queue")
        mock_factory_instance.create_topic_sender_client.assert_not_called()

        self.app.stop_server()

        self._assert_shutdown(server, thread, health_check)


@patch.dict(os.environ, ENV_VARS_TOPIC)
@patch("hl7_server.hl7_server_application.TCPHealthCheckServer")
@patch("hl7_server.hl7_server_application.MLLPServer")
@patch("hl7_server.hl7_server_application.ServiceBusClientFactory")
@patch("hl7_server.hl7_server_application.threading.Thread")
class TestHl7ServerApplicationTopic(unittest.TestCase):
    def setUp(self) -> None:
        self.app = Hl7ServerApplication()

    def _setup_mocks(self, mock_thread: MagicMock, mock_mllp_server: MLLPServer, mock_health_check: MagicMock) -> tuple[
        MagicMock, MagicMock, MagicMock]:
        mock_server_instance = MagicMock()
        mock_thread_instance = MagicMock()
        mock_health_instance = MagicMock()
        mock_mllp_server.return_value = mock_server_instance
        mock_thread.return_value = mock_thread_instance
        mock_health_check.return_value = mock_health_instance
        return mock_server_instance, mock_thread_instance, mock_health_instance

    def _assert_shutdown(self, server: MagicMock, thread: MagicMock, health_check: MagicMock) -> None:
        server.shutdown.assert_called_once()
        server.server_close.assert_called_once()
        thread.join.assert_called_once()
        health_check.stop.assert_called_once()

    def test_creates_topic_sender_client(self, mock_thread: MagicMock, mock_factory: MagicMock,
                                        mock_mllp_server: MLLPServer, mock_health_check: MagicMock) -> None:
        server, thread, health_check = self._setup_mocks(mock_thread, mock_mllp_server, mock_health_check)
        mock_factory_instance = mock_factory.return_value

        self.app.start_server()

        mock_factory_instance.create_topic_sender_client.assert_called_once_with("egress_topic")
        mock_factory_instance.create_queue_sender_client.assert_not_called()

        self.app.stop_server()

        self._assert_shutdown(server, thread, health_check)
