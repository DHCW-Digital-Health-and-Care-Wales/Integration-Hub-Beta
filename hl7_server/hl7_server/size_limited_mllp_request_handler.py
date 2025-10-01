import logging
import socket
from typing import Optional

from event_logger_lib.event_logger import EventLogger
from hl7apy.mllp import MLLPRequestHandler

logger = logging.getLogger(__name__)


class SizeLimitedMLLPRequestHandler(MLLPRequestHandler):
    def handle(self) -> None:
        max_message_size: int = getattr(self.server, 'max_message_size_bytes')
        event_logger: Optional[EventLogger] = getattr(self.server, 'event_logger', None)

        end_seq = self.eb + self.cr
        accumulated_data = b""

        buffer_size = min(8192, max_message_size // 4)  # 8KB or 1/4 of max size, whichever is smaller

        try:
            initial_data = self.request.recv(1)
            if not initial_data:
                return
            accumulated_data += initial_data
        except socket.timeout:
            self.request.close()
            return

        if not self._validate_start_block(initial_data):
            self.request.close()
            return

        while not self._has_end_sequence(accumulated_data, end_seq):
            try:
                # Check size limit before reading more data
                remaining_space = max_message_size - len(accumulated_data)
                if remaining_space <= 0:
                    self._handle_size_limit_exceeded(accumulated_data, max_message_size, event_logger)
                    return

                # Read next chunk, limited by remaining space
                chunk_size = min(buffer_size, remaining_space)
                chunk = self.request.recv(chunk_size)

                if not chunk:
                    break

                accumulated_data += chunk

                # Double-check size limit after adding chunk
                if len(accumulated_data) > max_message_size:
                    self._handle_size_limit_exceeded(accumulated_data, max_message_size, event_logger)
                    return

            except socket.timeout:
                self.request.close()
                return

        self._process_complete_message(accumulated_data, max_message_size)

    def _validate_start_block(self, data: bytes) -> bool:
        return len(data) > 0 and data[:1] == self.sb

    def _has_end_sequence(self, data: bytes, end_seq: bytes) -> bool:
        if len(data) < len(end_seq) + 1: # Need at least start block + content + end_seq
            return False

        return data[-len(end_seq):] == end_seq

    def _process_complete_message(self, accumulated_data: bytes, max_message_size: int) -> None:
        try:
            message_content = self._extract_hl7_message(accumulated_data.decode(self.encoding))
            if message_content is not None:
                logger.info(
                    f"Received message of size {len(accumulated_data)} bytes "
                    f"(within limit of {max_message_size} bytes)"
                )

                response = self._route_message(message_content)
                self.wfile.write(response.encode(self.encoding))

        except Exception as e:
            logger.error(f"Error processing message: {e}")
        finally:
            self.request.close()

    def _handle_size_limit_exceeded(
        self,
        accumulated_data: bytes,
        max_message_size: int,
        event_logger: Optional[EventLogger]
    ) -> None:
        error_msg = (
            f"Message size ({len(accumulated_data)} bytes) "
            f"exceeds maximum allowed size ({max_message_size} bytes). "
            "Connection will be closed."
        )
        logger.error(error_msg)

        if event_logger:
            try:
                partial_message = accumulated_data.decode('utf-8', errors='ignore')[:1000]
                event_logger.log_message_failed(
                    partial_message,
                    error_msg,
                    "Message size limit exceeded"
                )
            except Exception:
                pass

        self.request.close()
