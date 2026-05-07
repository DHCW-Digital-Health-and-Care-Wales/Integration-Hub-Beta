import logging
import socket
from typing import Optional

from event_logger_lib.event_logger import EventLogger
from hl7apy.exceptions import HL7apyException
from hl7apy.mllp import MLLPRequestHandler, UnsupportedMessageType
from hl7apy.parser import parse_message

from .hl7_nack_builder import HL7NackBuilder

logger = logging.getLogger(__name__)

MAX_PARTIAL_MESSAGE_LOG_SIZE = 1000
ADT_MESSAGE_CODE = "ADT"


class AdtMllpRequestHandler(MLLPRequestHandler):
    """MLLP request handler that enforces a message size limit and accepts only ADT message types."""

    def handle(self) -> None:
        max_message_size: int = getattr(self.server, "max_message_size_bytes")
        event_logger: Optional[EventLogger] = getattr(self.server, "event_logger", None)

        end_seq = self.eb + self.cr
        accumulated_data = b""
        buffer_size = max(1024, min(8192, max_message_size // 4))

        try:
            initial_data = self.request.recv(1)
            if not initial_data:
                return
            accumulated_data += initial_data
        except socket.timeout:
            self.request.close()
            return

        if not accumulated_data or accumulated_data[:1] != self.sb:
            self.request.close()
            return

        while not self._has_end_sequence(accumulated_data, end_seq):
            try:
                remaining_space = max_message_size - len(accumulated_data)
                if remaining_space <= 0:
                    self._handle_size_limit_exceeded(accumulated_data, max_message_size, event_logger)
                    return

                chunk_size = min(buffer_size, remaining_space)
                chunk = self.request.recv(chunk_size)

                if not chunk:
                    break

                accumulated_data += chunk

                if len(accumulated_data) > max_message_size:
                    self._handle_size_limit_exceeded(accumulated_data, max_message_size, event_logger)
                    return

            except socket.timeout:
                self.request.close()
                return

        self._process_complete_message(accumulated_data, max_message_size)

    def _has_end_sequence(self, data: bytes, end_seq: bytes) -> bool:
        if len(data) < len(end_seq) + 1:
            return False
        return data[-len(end_seq):] == end_seq

    def _process_complete_message(self, accumulated_data: bytes, max_message_size: int) -> None:
        try:
            message_content = self._extract_hl7_message(accumulated_data.decode(self.encoding))
            if message_content is not None:
                logger.info(
                    "Received message of size %d bytes (within limit of %d bytes)",
                    len(accumulated_data),
                    max_message_size,
                )
                response = self._route_message(message_content)
                self.wfile.write(response.encode(self.encoding))
        except Exception as e:
            logger.error("Error processing message: %s", e)
        finally:
            self.request.close()

    def _route_message(self, msg: str) -> str:
        try:
            m = parse_message(msg, find_groups=False)
            msg_code: str = m.msh.msh_9.msh_9_1.value
        except HL7apyException as e:
            logger.error("Failed to parse HL7 message for routing: %s", e)
            return self._build_error_response(e, msg)

        if msg_code != ADT_MESSAGE_CODE:
            exc = UnsupportedMessageType(
                f"Only ADT message types are accepted by this service, received: {msg_code}"
            )
            logger.error("Rejected non-ADT message: %s", msg_code)
            return self._build_error_response(exc, msg)

        try:
            handler_class, *args = self.server.handlers["ADT"]
            return handler_class(msg, *args).reply()
        except Exception as e:
            logger.error("Error processing ADT message: %s", e)
            return self._build_error_response(e, msg)

    def _build_error_response(self, exc: Exception, msg: str) -> str:
        if "ERR" in self.server.handlers:
            handler_class, *args = self.server.handlers["ERR"]
            return handler_class(exc, msg, *args).reply()
        nack_builder = HL7NackBuilder()
        return nack_builder.build_nack(msg).to_mllp()

    def _handle_size_limit_exceeded(
        self,
        accumulated_data: bytes,
        max_message_size: int,
        event_logger: Optional[EventLogger],
    ) -> None:
        error_msg = (
            f"Message size ({len(accumulated_data)} bytes) exceeds maximum allowed size "
            f"({max_message_size} bytes). Connection will be closed."
        )
        logger.error(error_msg)

        if event_logger:
            try:
                partial_message = accumulated_data[:MAX_PARTIAL_MESSAGE_LOG_SIZE].decode("utf-8", errors="ignore")
                event_logger.log_message_failed(partial_message, error_msg, "Message size limit exceeded")
            except Exception:
                pass

        self.request.close()
