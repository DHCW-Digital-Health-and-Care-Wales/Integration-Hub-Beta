import unittest
from unittest.mock import Mock, patch

from event_logger_lib.event_logger import EventLogger

from hl7_server.app_config import AppConfig
from hl7_server.generic_handler import GenericHandler
from hl7_server.hl7_validator import HL7Validator
from hl7_server.size_limited_mllp_server import SizeLimitedMLLPServer


class TestMessageSizeLimit(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_sender_client = Mock()
        self.mock_event_logger = Mock(spec=EventLogger)
        self.mock_validator = Mock(spec=HL7Validator)
        self.test_host = "127.0.0.1"
        self.test_port = 9999
        self.test_message_size_limit = 100

        self.test_handlers = {
            "ADT^A31^ADT_A05": (
                GenericHandler,
                self.mock_sender_client,
                self.mock_event_logger,
                self.mock_validator,
                "test_flow"
            ),
        }

    def test_message_within_size_limit_accepted(self) -> None:
        server = SizeLimitedMLLPServer(
            self.test_host,
            self.test_port,
            self.test_handlers,
            max_message_size_bytes=1000,
            event_logger=self.mock_event_logger
        )

        self.assertEqual(server.max_message_size_bytes, 1000)

    def test_app_config_default_message_size(self) -> None:
        with patch.dict('os.environ', {
            'EGRESS_QUEUE_NAME': 'test-queue',
            'AUDIT_QUEUE_NAME': 'audit-queue',
            'WORKFLOW_ID': 'test-workflow',
            'MICROSERVICE_ID': 'test-service'
        }):
            config = AppConfig.read_env_config()
            self.assertEqual(config.max_message_size_bytes, 1048576)  # 1MB default

    def test_app_config_custom_message_size(self) -> None:
        with patch.dict('os.environ', {
            'EGRESS_QUEUE_NAME': 'test-queue',
            'AUDIT_QUEUE_NAME': 'audit-queue',
            'WORKFLOW_ID': 'test-workflow',
            'MICROSERVICE_ID': 'test-service',
            'MAX_MESSAGE_SIZE_BYTES': '2097152'  # 2MB
        }):
            config = AppConfig.read_env_config()
            self.assertEqual(config.max_message_size_bytes, 2097152)

    def test_server_initialization_with_custom_size_limit(self) -> None:
        custom_size = 512000  # 500KB

        server = SizeLimitedMLLPServer(
            self.test_host,
            self.test_port + 1,
            self.test_handlers,
            max_message_size_bytes=custom_size,
            event_logger=self.mock_event_logger
        )

        self.assertEqual(server.max_message_size_bytes, custom_size)
        self.assertEqual(server.event_logger, self.mock_event_logger)

    def tearDown(self) -> None:
        pass


if __name__ == '__main__':
    unittest.main()
