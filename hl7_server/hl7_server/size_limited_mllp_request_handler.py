import logging
import socket
from typing import Optional

from event_logger_lib.event_logger import EventLogger
from hl7apy.mllp import MLLPRequestHandler

logger = logging.getLogger(__name__)


class SizeLimitedMLLPRequestHandler(MLLPRequestHandler):
    def handle(self) -> None:
        max_message_size: int = getattr(self.server, 'max_message_size_bytes', 1048576)
        event_logger: Optional[EventLogger] = getattr(self.server, 'event_logger', None)

        end_seq = self.eb + self.cr
        accumulated_data = b""

        try:
            line = self.request.recv(3)
            if not line:
                self.request.close()
                return
            accumulated_data += line
        except socket.timeout:
            self.request.close()
            return

        if line[:1] != self.sb:
            self.request.close()
            return

        while accumulated_data[-2:] != end_seq:
            try:
                char = self.rfile.read(1)
                if not char:
                    break
                accumulated_data += char

                if len(accumulated_data) > max_message_size:
                    error_msg = (
                        f"Message size ({len(accumulated_data)} bytes) "
                        f"exceeds maximum allowed size ({max_message_size} bytes). "
                        "Connection will be closed."
                    )
                    logger.error(error_msg)

                    if event_logger:
                        try:
                            partial_message = accumulated_data.decode('utf-8', errors='ignore')[:1000]
                            event_logger.log_message_failed(partial_message, error_msg, "Message size limit exceeded")
                        except Exception:
                            pass

                    self.request.close()
                    return

            except socket.timeout:
                self.request.close()
                return

        message_content = self._extract_hl7_message(accumulated_data.decode(self.encoding))
        if message_content is not None:
            logger.info(
                f"Received message of size {len(accumulated_data)} bytes "
                f"(within limit of {max_message_size} bytes)"
            )

            try:
                response = self._route_message(message_content)
                self.wfile.write(response.encode(self.encoding))
            except Exception:
                pass

        self.request.close()
