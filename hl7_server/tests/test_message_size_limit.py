import unittest
from typing import List
from unittest.mock import Mock, patch

from event_logger_lib.event_logger import EventLogger

from hl7_server.app_config import AppConfig
from hl7_server.generic_handler import GenericHandler
from hl7_server.hl7_validator import HL7Validator
from hl7_server.size_limited_mllp_request_handler import SizeLimitedMLLPRequestHandler
from hl7_server.size_limited_mllp_server import SizeLimitedMLLPServer


class TestMessageSizeLimit(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_sender_client = Mock()
        self.mock_event_logger = Mock(spec=EventLogger)
        self.mock_validator = Mock(spec=HL7Validator)
        self.test_host = "127.0.0.1"
        self.test_port = 9999
        self.test_message_size_limit = 100

        self.start_block = b'\x0b'      # MLLP start block (ASCII 11)
        self.end_block = b'\x1c'        # MLLP end block (ASCII 28)
        self.carriage_return = b'\r'    # MLLP carriage return (ASCII 13)

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

    def test_app_config_service_bus_limit_exceeded(self) -> None:
        with patch.dict('os.environ', {
            'EGRESS_QUEUE_NAME': 'test-queue',
            'AUDIT_QUEUE_NAME': 'audit-queue',
            'WORKFLOW_ID': 'test-workflow',
            'MICROSERVICE_ID': 'test-service',
            'MAX_MESSAGE_SIZE_BYTES': '104857601'  # 1 byte over 100MB limit
        }, clear=True):
            with self.assertRaises(ValueError) as context:
                AppConfig.read_env_config()

            error_message = str(context.exception)
            self.assertIn("exceeds Azure Service Bus Premium tier limit", error_message)
            self.assertIn("104857600 bytes", error_message)
            self.assertIn("100.0MB", error_message)

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

    @patch('hl7_server.size_limited_mllp_request_handler.logger')
    def test_connection_closed_when_message_exceeds_size_limit(self, mock_logger: Mock) -> None:
        handler = object.__new__(SizeLimitedMLLPRequestHandler)

        mock_server = Mock()
        mock_server.max_message_size_bytes = 50  # Very small limit for testing
        mock_server.event_logger = self.mock_event_logger
        handler.server = mock_server

        mock_request = Mock()
        mock_wfile = Mock()
        handler.request = mock_request
        handler.wfile = mock_wfile

        handler.sb = self.start_block  # Start block
        handler.eb = self.end_block    # End block
        handler.cr = self.carriage_return  # Carriage return
        handler.encoding = 'utf-8'

        oversized_content = "X" * 100

        message_chunks: List[bytes] = [
            self.start_block,  # First chunk: start block (1 byte)
            oversized_content[:30].encode('utf-8'),  # Second chunk: partial content (30 bytes, total: 31)
            oversized_content[30:].encode('utf-8')   # Third chunk: remaining content (triggers 50-byte limit)
        ]

        mock_request.recv.side_effect = message_chunks

        handler.handle()

        mock_request.close.assert_called_once()

        mock_logger.error.assert_called()
        error_call_args = mock_logger.error.call_args[0][0]
        self.assertIn("exceeds maximum allowed size", error_call_args)
        self.assertIn("50 bytes", error_call_args)

        self.mock_event_logger.log_message_failed.assert_called_once()
        event_log_args = self.mock_event_logger.log_message_failed.call_args
        self.assertIn("Message size limit exceeded", event_log_args[0])

        self.assertGreaterEqual(mock_request.recv.call_count, 2)

    @patch('hl7_server.size_limited_mllp_request_handler.logger')
    def test_valid_message_processed_successfully_without_closure(self, mock_logger: Mock) -> None:
        handler = object.__new__(SizeLimitedMLLPRequestHandler)

        mock_server = Mock()
        mock_server.max_message_size_bytes = 1000  # 1KB limit
        mock_server.event_logger = self.mock_event_logger
        handler.server = mock_server

        mock_request = Mock()
        mock_wfile = Mock()
        handler.request = mock_request
        handler.wfile = mock_wfile

        handler.sb = self.start_block
        handler.eb = self.end_block
        handler.cr = self.carriage_return
        handler.encoding = 'utf-8'

        # Create valid message within size limit
        message_content = (
            "MSH|^~\\&|SENDING_APP|SENDING_FACILITY|RECEIVING_APP|RECEIVING_FACILITY|"
            "20250101120000||ADT^A31^ADT_A05|12345|P|2.5"
        )
        complete_message = self.start_block + message_content.encode('utf-8') + self.end_block + self.carriage_return

        message_chunks = [
            self.start_block,  # First chunk: start block
            message_content[:50].encode('utf-8'),  # Second chunk: partial content
            message_content[50:].encode('utf-8'),  # Third chunk: remaining content
            self.end_block + self.carriage_return,  # Fourth chunk: end sequence
            b''  # Fifth chunk: empty (end of transmission)
        ]

        mock_request.recv.side_effect = message_chunks

        handler._extract_hl7_message = Mock(return_value=message_content)
        handler._route_message = Mock(return_value="ACK|12345|P|2.5")

        handler.handle()

        handler._extract_hl7_message.assert_called_once_with(complete_message.decode('utf-8'))
        handler._route_message.assert_called_once_with(message_content)

        mock_wfile.write.assert_called_once()
        written_response = mock_wfile.write.call_args[0][0]
        self.assertIn(b"ACK", written_response)

        mock_request.close.assert_called_once()

        mock_logger.info.assert_called()
        info_call_args = mock_logger.info.call_args[0][0]
        self.assertIn("Received message of size", info_call_args)
        self.assertIn("within limit", info_call_args)

        self.mock_event_logger.log_message_failed.assert_not_called()

    def tearDown(self) -> None:
        pass


if __name__ == '__main__':
    unittest.main()
