import unittest
from unittest.mock import MagicMock, patch

from adt_receiver.adt_receiver_application import AdtReceiverApplication

REQUIRED_ENV = {
    "EGRESS_QUEUE_NAME": "adt-queue",
    "AUDIT_QUEUE_NAME": "audit-queue",
    "WORKFLOW_ID": "test-workflow",
    "MICROSERVICE_ID": "test-microservice",
    "HEALTH_BOARD": "test-health-board",
    "PEER_SERVICE": "test-service",
}


class TestAdtReceiverApplication(unittest.TestCase):

    @patch("adt_receiver.adt_receiver_application.AdtMllpServer")
    @patch("adt_receiver.adt_receiver_application.TCPHealthCheckServer")
    @patch("adt_receiver.adt_receiver_application.ServiceBusClientFactory")
    @patch("adt_receiver.adt_receiver_application.EventLogger")
    @patch("adt_receiver.adt_receiver_application.MetricSender")
    @patch("adt_receiver.adt_receiver_application.AppConfig.read_env_config")
    def test_start_server_with_queue(
        self,
        mock_read_config: MagicMock,
        mock_metric_sender: MagicMock,
        mock_event_logger: MagicMock,
        mock_factory_cls: MagicMock,
        mock_health_cls: MagicMock,
        mock_server_cls: MagicMock,
    ) -> None:
        config = MagicMock()
        config.egress_queue_name = "adt-queue"
        config.egress_topic_name = None
        config.egress_session_id = None
        config.max_message_size_bytes = 1048576
        mock_read_config.return_value = config

        mock_server = MagicMock()
        mock_server_cls.return_value = mock_server

        app = AdtReceiverApplication()
        app.start_server()

        mock_server_cls.assert_called_once()
        mock_server.serve_forever.assert_called_once()

    @patch("adt_receiver.adt_receiver_application.AdtMllpServer")
    @patch("adt_receiver.adt_receiver_application.TCPHealthCheckServer")
    @patch("adt_receiver.adt_receiver_application.ServiceBusClientFactory")
    @patch("adt_receiver.adt_receiver_application.EventLogger")
    @patch("adt_receiver.adt_receiver_application.MetricSender")
    @patch("adt_receiver.adt_receiver_application.AppConfig.read_env_config")
    def test_start_server_with_topic(
        self,
        mock_read_config: MagicMock,
        mock_metric_sender: MagicMock,
        mock_event_logger: MagicMock,
        mock_factory_cls: MagicMock,
        mock_health_cls: MagicMock,
        mock_server_cls: MagicMock,
    ) -> None:
        config = MagicMock()
        config.egress_queue_name = None
        config.egress_topic_name = "adt-topic"
        config.max_message_size_bytes = 1048576
        mock_read_config.return_value = config

        mock_server = MagicMock()
        mock_server_cls.return_value = mock_server

        app = AdtReceiverApplication()
        app.start_server()

        factory_instance = mock_factory_cls.return_value
        factory_instance.create_topic_sender_client.assert_called_once_with("adt-topic")

    @patch("adt_receiver.adt_receiver_application.AdtMllpServer")
    @patch("adt_receiver.adt_receiver_application.TCPHealthCheckServer")
    @patch("adt_receiver.adt_receiver_application.ServiceBusClientFactory")
    @patch("adt_receiver.adt_receiver_application.EventLogger")
    @patch("adt_receiver.adt_receiver_application.MetricSender")
    @patch("adt_receiver.adt_receiver_application.AppConfig.read_env_config")
    def test_stop_server_shuts_down_all_components(
        self,
        mock_read_config: MagicMock,
        mock_metric_sender: MagicMock,
        mock_event_logger: MagicMock,
        mock_factory_cls: MagicMock,
        mock_health_cls: MagicMock,
        mock_server_cls: MagicMock,
    ) -> None:
        config = MagicMock()
        config.egress_queue_name = "adt-queue"
        config.egress_topic_name = None
        config.egress_session_id = None
        config.max_message_size_bytes = 1048576
        mock_read_config.return_value = config

        mock_server = MagicMock()
        mock_server_cls.return_value = mock_server

        app = AdtReceiverApplication()
        app.start_server()
        app.stop_server()

        mock_server.shutdown.assert_called_once()
        mock_server.server_close.assert_called_once()

    def test_default_port_is_3475(self) -> None:
        app = AdtReceiverApplication()
        self.assertEqual(app.PORT, 3475)

    @patch("adt_receiver.adt_receiver_application.os.environ.get")
    def test_port_can_be_overridden_via_env(self, mock_env_get: MagicMock) -> None:
        mock_env_get.side_effect = lambda key, default=None: "4000" if key == "PORT" else default
        app = AdtReceiverApplication()
        self.assertEqual(app.PORT, 4000)


if __name__ == "__main__":
    unittest.main()
