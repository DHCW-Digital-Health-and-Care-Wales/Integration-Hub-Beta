import unittest
from typing import List
from unittest.mock import Mock, patch

from event_logger_lib.event_logger import EventLogger

from hl7_server.size_limited_mllp_request_handler import SizeLimitedMLLPRequestHandler


class TestSizeLimitedMLLPRequestHandler(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_event_logger = Mock(spec=EventLogger)

        self.start_block = b'\x0b'      # MLLP start block (ASCII 11)
        self.end_block = b'\x1c'        # MLLP end block (ASCII 28)
        self.carriage_return = b'\r'    # MLLP carriage return (ASCII 13)

    def _create_handler_instance(self, max_size: int) -> SizeLimitedMLLPRequestHandler:

        handler = object.__new__(SizeLimitedMLLPRequestHandler)

        mock_server = Mock()
        mock_server.max_message_size_bytes = max_size
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

        return handler

    @patch('hl7_server.size_limited_mllp_request_handler.logger')
    def test_connection_closed_when_message_exceeds_size_limit(self, mock_logger: Mock) -> None:
        handler = self._create_handler_instance(max_size=50)  # Very small limit for testing

        oversized_content = "X" * 100  # Content that exceeds limit

        message_chunks: List[bytes] = [
            self.start_block,  # First chunk: start block (1 byte)
            oversized_content[:30].encode('utf-8'),  # Second chunk: 30 bytes (total: 31)
            oversized_content[30:].encode('utf-8')   # Third chunk: triggers 50-byte limit
        ]

        handler.request.recv.side_effect = message_chunks

        handler.handle()

        handler.request.close.assert_called_once()

        mock_logger.error.assert_called()
        error_call_args = mock_logger.error.call_args[0][0]
        self.assertIn("exceeds maximum allowed size", error_call_args)
        self.assertIn("50 bytes", error_call_args)

        self.mock_event_logger.log_message_failed.assert_called_once()
        event_log_args = self.mock_event_logger.log_message_failed.call_args[0]
        self.assertIn("Message size limit exceeded", event_log_args[2])

        self.assertGreaterEqual(handler.request.recv.call_count, 2)

    @patch('hl7_server.size_limited_mllp_request_handler.logger')
    def test_valid_message_processed_successfully_without_closure(self, mock_logger: Mock) -> None:
        handler = self._create_handler_instance(max_size=1000)  # 1KB limit

        # Message within size limit
        message_content = (
            "MSH|^~\\&|SENDING_APP|SENDING_FACILITY|RECEIVING_APP|RECEIVING_FACILITY|"
            "20250101120000||ADT^A31^ADT_A05|12345|P|2.5"
        )
        complete_message = (
            self.start_block +
            message_content.encode('utf-8') +
            self.end_block +
            self.carriage_return
        )

        message_chunks: List[bytes] = [
            self.start_block,  # First chunk: start block
            message_content[:50].encode('utf-8'),  # Second chunk: partial content
            message_content[50:].encode('utf-8'),  # Third chunk: remaining content
            self.end_block + self.carriage_return,  # Fourth chunk: end sequence
            b''  # Fifth chunk: empty (end of transmission)
        ]

        handler.request.recv.side_effect = message_chunks

        handler._extract_hl7_message = Mock(return_value=message_content)
        handler._route_message = Mock(return_value="ACK|12345|P|2.5")

        handler.handle()

        handler._extract_hl7_message.assert_called_once_with(complete_message.decode('utf-8'))
        handler._route_message.assert_called_once_with(message_content)

        handler.wfile.write.assert_called_once()
        written_response = handler.wfile.write.call_args[0][0]
        self.assertIn(b"ACK", written_response)

        handler.request.close.assert_called_once()

        mock_logger.info.assert_called()
        info_call_args = mock_logger.info.call_args[0][0]
        self.assertIn("Received message of size", info_call_args)
        self.assertIn("within limit", info_call_args)

        self.mock_event_logger.log_message_failed.assert_not_called()


if __name__ == '__main__':
    unittest.main()
