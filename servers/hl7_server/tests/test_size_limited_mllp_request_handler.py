import re
import unittest
from typing import List
from unittest.mock import Mock, patch

from event_logger_lib.event_logger import EventLogger

from hl7_server.hl7_ack_builder import HL7AckBuilder
from hl7_server.size_limited_mllp_request_handler import SizeLimitedMLLPRequestHandler


class TestSizeLimitedMLLPRequestHandler(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_event_logger = Mock(spec=EventLogger)
        self.ack_builder = HL7AckBuilder()

        self.start_block = b'\x0b'      # MLLP start block (ASCII 11)
        self.end_block = b'\x1c'        # MLLP end block (ASCII 28)
        self.carriage_return = b'\r'    # MLLP carriage return (ASCII 13)

    def _create_handler_instance(self, max_size: int) -> SizeLimitedMLLPRequestHandler:

        handler = object.__new__(SizeLimitedMLLPRequestHandler)

        mock_server = Mock()
        mock_server.max_message_size_bytes = max_size
        mock_server.event_logger = self.mock_event_logger
        mock_server.ack_builder = self.ack_builder
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
    def test_ae_nack_sent_when_message_exceeds_size_limit(self, mock_logger: Mock) -> None:
        handler = self._create_handler_instance(max_size=50)

        oversized_content = "X" * 100

        message_chunks: List[bytes] = [
            self.start_block,
            oversized_content[:30].encode('utf-8'),
            oversized_content[30:].encode('utf-8')
        ]

        handler.request.recv.side_effect = message_chunks

        handler.handle()

        handler.wfile.write.assert_called_once()
        written_response = handler.wfile.write.call_args[0][0].decode('utf-8')
        self.assertTrue(written_response.startswith("\x0b"))
        self.assertTrue(written_response.endswith("\x1c\r"))
        self.assertIn("MSA|AE|", written_response)

        handler.request.close.assert_called_once()

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
        info_call_messages = [call.args[0] for call in mock_logger.info.call_args_list]
        self.assertTrue(any("Received message of size" in msg and "within limit" in msg for msg in info_call_messages))
        self.assertTrue(any("Response of 15 chars written to client" in msg for msg in info_call_messages))

        self.mock_event_logger.log_message_failed.assert_not_called()

    @patch('hl7_server.size_limited_mllp_request_handler.logger')
    def test_fallback_ae_nack_sent_when_route_message_raises_unexpectedly(self, mock_logger: Mock) -> None:
        # Simulates an exception escaping the registered ERR handler entirely (e.g. a decode
        # failure, or the ERR handler itself failing) - the top-level handler must still respond
        # with a NACK rather than silently closing the connection.
        handler = self._create_handler_instance(max_size=1000)

        message_content = "MSH|^~\\&|SENDING_APP|SENDING_FACILITY||||20250101120000||ADT^A31^ADT_A05|12345|P|2.5"
        message_chunks: List[bytes] = [
            self.start_block,
            message_content.encode('utf-8'),
            self.end_block + self.carriage_return,
            b''
        ]
        handler.request.recv.side_effect = message_chunks

        handler._extract_hl7_message = Mock(return_value=message_content)
        handler._route_message = Mock(side_effect=RuntimeError("ERR handler itself failed"))

        handler.handle()

        handler.wfile.write.assert_called_once()
        written_response = handler.wfile.write.call_args[0][0].decode('utf-8')
        self.assertTrue(written_response.startswith("\x0b"))
        self.assertTrue(written_response.endswith("\x1c\r"))
        self.assertIn("MSA|AE|", written_response)

        handler.request.close.assert_called_once()

    @patch('hl7_server.size_limited_mllp_request_handler.logger')
    def test_no_nack_double_write_when_fallback_nack_itself_fails(self, mock_logger: Mock) -> None:
        handler = self._create_handler_instance(max_size=1000)
        handler.server.ack_builder.build_generic_nack = Mock(side_effect=RuntimeError("nack build failed"))

        message_content = "MSH|^~\\&|SENDING_APP|SENDING_FACILITY||||20250101120000||ADT^A31^ADT_A05|12345|P|2.5"
        message_chunks: List[bytes] = [
            self.start_block,
            message_content.encode('utf-8'),
            self.end_block + self.carriage_return,
            b''
        ]
        handler.request.recv.side_effect = message_chunks

        handler._extract_hl7_message = Mock(return_value=message_content)
        handler._route_message = Mock(side_effect=RuntimeError("ERR handler itself failed"))

        # Must not raise even though both the primary processing and the fallback NACK fail.
        handler.handle()

        handler.wfile.write.assert_not_called()
        handler.request.close.assert_called_once()

    def _handle_raw_payload(self, payload: str) -> SizeLimitedMLLPRequestHandler:
        # Uses the real hl7apy framing regex (no mocked _extract_hl7_message).
        handler = self._create_handler_instance(max_size=1000)
        handler.validator = re.compile(
            "".join(["\x0b", r"(([^\r]+\r)*([^\r]+\r?))", "\x1c", "\r"])
        )
        handler.request.recv.side_effect = [b"\x0b", payload.encode("utf-8") + b"\x1c\r", b""]
        handler.handle()
        return handler

    @patch('hl7_server.size_limited_mllp_request_handler.logger')
    def test_ae_nack_with_empty_segment_reason_and_original_control_id(self, mock_logger: Mock) -> None:
        # Edge case: blank lines between segments produce "\r\r", which the framing regex rejects.
        payload = "MSH|^~\\&|129|129|100|100|20261104154202||ADT^A28^ADT_A05|CTRL-1|P|2.5\r\rEVN||20190202063500"

        handler = self._handle_raw_payload(payload)

        handler.wfile.write.assert_called_once()
        response = handler.wfile.write.call_args[0][0].decode("utf-8")
        self.assertIn("MSA|AE|CTRL-1|", response)
        self.assertIn("empty segment", response)
        mock_logger.error.assert_called()
        self.mock_event_logger.log_message_failed.assert_called_once()
        self.assertEqual("Malformed HL7 message framing", self.mock_event_logger.log_message_failed.call_args[0][2])
        handler.request.close.assert_called_once()

    @patch('hl7_server.size_limited_mllp_request_handler.logger')
    def test_ae_nack_generic_framing_reason_when_no_blank_segments(self, mock_logger: Mock) -> None:
        # Edge case: empty payload fails the regex without containing blank segments (no MSH either).
        handler = self._handle_raw_payload("")

        handler.wfile.write.assert_called_once()
        response = handler.wfile.write.call_args[0][0].decode("utf-8")
        self.assertIn("MSA|AE|", response)
        self.assertNotIn("empty segment", response)
        self.assertIn("segment framing", response)

    def test_extract_control_id(self) -> None:
        handler = self._create_handler_instance(max_size=1000)

        self.assertEqual("ABC", handler._extract_control_id("MSH|^~\\&|A|B|C|D|2026||ADT^A01|ABC|P|2.5\r\rPID|1"))
        self.assertIsNone(handler._extract_control_id("MSH|^~\\&|A|B"))  # too few fields
        self.assertIsNone(handler._extract_control_id("PID|1|2"))  # not an MSH segment
        self.assertIsNone(handler._extract_control_id(""))


if __name__ == '__main__':
    unittest.main()
