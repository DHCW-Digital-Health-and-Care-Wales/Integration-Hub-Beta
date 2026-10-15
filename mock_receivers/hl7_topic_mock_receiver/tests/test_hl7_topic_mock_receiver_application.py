import os
import signal
import unittest
from unittest.mock import MagicMock, patch

from hl7_topic_mock_receiver.hl7_topic_mock_receiver_application import Hl7TopicMockReceiver

ENV_VARS = {
    "HOST": "127.0.0.1",
    "PORT": "2576",
    "EGRESS_TOPIC_NAME": "egress_topic",
    "EGRESS_SESSION_ID": "mock",
    "SERVICE_BUS_CONNECTION_STRING": "Endpoint=sb://localhost",
    "HEALTH_CHECK_HOST": "127.0.0.1",
    "HEALTH_CHECK_PORT": "9000",
}


@patch.dict(os.environ, ENV_VARS)
@patch("hl7_topic_mock_receiver.hl7_topic_mock_receiver_application.TCPHealthCheckServer")
@patch("hl7_topic_mock_receiver.hl7_topic_mock_receiver_application.MLLPServer")
@patch("hl7_topic_mock_receiver.hl7_topic_mock_receiver_application.ServiceBusClientFactory")
@patch("hl7_topic_mock_receiver.hl7_topic_mock_receiver_application.threading.Thread")
class TestHl7TopicServerApplication(unittest.TestCase):
    def setUp(self) -> None:
        self.app = Hl7TopicMockReceiver()

    def _setup_mocks(
        self, mock_thread: MagicMock, mock_custom_mllp_server: MagicMock, mock_health_check: MagicMock
    ) -> tuple[MagicMock, MagicMock, MagicMock]:
        mock_server_instance = MagicMock()
        mock_thread_instance = MagicMock()
        mock_health_instance = MagicMock()
        mock_custom_mllp_server.return_value = mock_server_instance
        mock_thread.return_value = mock_thread_instance
        mock_health_check.return_value = mock_health_instance
        return mock_server_instance, mock_thread_instance, mock_health_instance

    def _assert_shutdown(self, server: MagicMock, thread: MagicMock, health_check: MagicMock) -> None:
        server.shutdown.assert_called_once()
        server.server_close.assert_called_once()
        thread.join.assert_called_once()
        health_check.stop.assert_called_once()

    def test_server_initialization_and_shutdown(
        self, mock_thread: MagicMock, _: MagicMock, mock_custom_mllp_server: MagicMock, mock_health_check: MagicMock
    ) -> None:
        server, thread, health_check = self._setup_mocks(mock_thread, mock_custom_mllp_server, mock_health_check)
        self.app.start_server()
        self.app.stop_server()

        self._assert_shutdown(server, thread, health_check)

    def test_signal_handler_shutdown(
        self, mock_thread: MagicMock, _: MagicMock, mock_custom_mllp_server: MagicMock, mock_health_check: MagicMock
    ) -> None:
        server, thread, health_check = self._setup_mocks(mock_thread, mock_custom_mllp_server, mock_health_check)
        self.app.start_server()
        self.app._signal_handler(signal.SIGINT, None)

        self._assert_shutdown(server, thread, health_check)

    def test_server_exception_handling(
        self, mock_thread: MagicMock, _: MagicMock, mock_custom_mllp_server: MagicMock, mock_health_check: MagicMock
    ) -> None:
        server, thread, health_check = self._setup_mocks(mock_thread, mock_custom_mllp_server, mock_health_check)
        thread.start.side_effect = RuntimeError("Simulated server error")
        thread.is_alive.return_value = False
        thread.ident = None

        with self.assertRaises(RuntimeError):
            self.app.start_server()

        # The thread never actually started running serve_forever, so shutdown() (which waits
        # for the loop to exit) and join() (which requires a started thread) must be skipped -
        # only the listener socket should be closed.
        server.shutdown.assert_not_called()
        server.server_close.assert_called_once()
        thread.join.assert_not_called()
        health_check.stop.assert_called_once()

    def test_health_check_initialization(
        self, mock_thread: MagicMock, _: MagicMock, mock_custom_mllp_server: MagicMock, mock_health_check: MagicMock
    ) -> None:
        server, thread, health_check = self._setup_mocks(mock_thread, mock_custom_mllp_server, mock_health_check)

        self.app.start_server()

        mock_health_check.assert_called_once_with("127.0.0.1", 9000)
        health_check.start.assert_called_once()

        self.app.stop_server()
        self._assert_shutdown(server, thread, health_check)

    def test_start_server_uses_topic_sender_client(
        self,
        mock_thread: MagicMock,
        mock_factory: MagicMock,
        mock_custom_mllp_server: MagicMock,
        mock_health_check: MagicMock,
    ) -> None:
        self._setup_mocks(mock_thread, mock_custom_mllp_server, mock_health_check)
        self.app.start_server()

        mock_factory.return_value.create_topic_sender_client.assert_called_once_with("egress_topic", "mock")


@patch.dict(os.environ, {"HOST": "127.0.0.1", "PORT": "2576"}, clear=True)
@patch("hl7_topic_mock_receiver.hl7_topic_mock_receiver_application.TCPHealthCheckServer")
@patch("hl7_topic_mock_receiver.hl7_topic_mock_receiver_application.MLLPServer")
@patch("hl7_topic_mock_receiver.hl7_topic_mock_receiver_application.ServiceBusClientFactory")
@patch("hl7_topic_mock_receiver.hl7_topic_mock_receiver_application.threading.Thread")
class TestHl7TopicServerApplicationWithoutServiceBus(unittest.TestCase):
    """No EGRESS_TOPIC_NAME/connection info configured - e.g. standalone via the tester's
    Mock Receiver bar - the server should still start and skip Service Bus wiring entirely."""

    def setUp(self) -> None:
        self.app = Hl7TopicMockReceiver()
        self.addCleanup(self.app.stop_server)

    def test_start_server_skips_service_bus_client_factory(
        self,
        mock_thread: MagicMock,
        mock_factory: MagicMock,
        mock_custom_mllp_server: MagicMock,
        mock_health_check: MagicMock,
    ) -> None:
        mock_custom_mllp_server.return_value = MagicMock()
        mock_thread.return_value = MagicMock()
        mock_health_check.return_value = MagicMock()

        self.app.start_server()

        mock_factory.assert_not_called()
        self.assertIsNone(self.app.sender_client)
