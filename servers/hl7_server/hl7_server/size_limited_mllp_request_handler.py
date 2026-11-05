import logging
import socket
from typing import Optional

from event_logger_lib.event_logger import EventLogger
from hl7apy.mllp import MLLPRequestHandler

from hl7_server.hl7_ack_builder import HL7AckBuilder

logger = logging.getLogger(__name__)

MAX_PARTIAL_MESSAGE_LOG_SIZE = 1000
MAX_CONTROL_ID_LENGTH = 199  # MSH-10 length limit


class SizeLimitedMLLPRequestHandler(MLLPRequestHandler):
    def handle(self) -> None:
        max_message_size: int = getattr(self.server, 'max_message_size_bytes')
        event_logger: Optional[EventLogger] = getattr(self.server, 'event_logger', None)
        ack_builder: Optional[HL7AckBuilder] = getattr(self.server, 'ack_builder', None)

        end_seq = self.eb + self.cr
        accumulated_data = b""

        buffer_size = max(1024, min(8192, max_message_size // 4))  # 1KB-8KB range, or 1/4 of max size

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
                    self._handle_size_limit_exceeded(accumulated_data, max_message_size, event_logger, ack_builder)
                    return

                # Read next chunk, limited by remaining space
                chunk_size = min(buffer_size, remaining_space)
                chunk = self.request.recv(chunk_size)

                if not chunk:
                    break

                accumulated_data += chunk

                # Double-check size limit after adding chunk
                if len(accumulated_data) > max_message_size:
                    self._handle_size_limit_exceeded(accumulated_data, max_message_size, event_logger, ack_builder)
                    return

            except socket.timeout:
                self.request.close()
                return

        self._process_complete_message(accumulated_data, max_message_size, ack_builder, event_logger)

    def _validate_start_block(self, data: bytes) -> bool:
        return len(data) > 0 and data[:1] == self.sb

    def _has_end_sequence(self, data: bytes, end_seq: bytes) -> bool:
        if len(data) < len(end_seq) + 1: # Need at least start block + content + end_seq
            return False

        return data[-len(end_seq):] == end_seq

    def _process_complete_message(
        self,
        accumulated_data: bytes,
        max_message_size: int,
        ack_builder: Optional[HL7AckBuilder] = None,
        event_logger: Optional[EventLogger] = None,
    ) -> None:
        try:
            raw_message = accumulated_data.decode(self.encoding)
            message_content = self._extract_hl7_message(raw_message)
            if message_content is None:
                self._handle_malformed_message(raw_message, event_logger, ack_builder)
            else:
                logger.info(
                    f"Received message of size {len(accumulated_data)} bytes "
                    f"(within limit of {max_message_size} bytes)"
                )

                response = self._route_message(message_content)
                self.wfile.write(response.encode(self.encoding))
                # Positive confirmation the response (ACK or NACK) was written to the socket -
                # without this, "no error logged" could otherwise be misread as proof of delivery.
                logger.info(f"Response of {len(response)} chars written to client")

        except Exception as e:
            # This is a last resort: the registered ERR handler (see error_handler.ErrorHandler)
            # already turns validation/parsing/unexpected failures into a NACK before they reach
            # here. This branch only catches what escapes that path entirely - e.g. a decode
            # failure before parsing, or the ERR handler itself failing - so a NACK still reaches
            # the sender instead of the connection being silently closed.
            logger.error(f"Error processing message: {e}")
            self._send_fallback_nack(f"Unexpected error while processing message: {e}", ack_builder)
        finally:
            self.request.close()

    def _handle_malformed_message(
        self, raw_message: str, event_logger: Optional[EventLogger], ack_builder: Optional[HL7AckBuilder]
    ) -> None:
        # hl7apy's framing regex rejects the payload without raising, which would otherwise close the
        # connection with no log and no NACK. Report the cause so the sender isn't left guessing.
        payload = raw_message[len(self.sb):] if raw_message.startswith(self.sb.decode(self.encoding)) else raw_message
        payload = payload.removesuffix(self.eb.decode(self.encoding) + self.cr.decode(self.encoding))

        if self.cr.decode(self.encoding) * 2 in payload or payload.startswith(self.cr.decode(self.encoding)):
            reason = (
                "Malformed HL7 message: empty segment(s) found (consecutive or leading segment terminators). "
                "Each segment must be non-empty and separated by a single <CR>."
            )
        else:
            reason = "Malformed HL7 message: payload does not conform to MLLP/HL7 segment framing."

        logger.error(f"{reason} Received {len(raw_message)} bytes; returning AE NACK.")

        if event_logger:
            try:
                event_logger.log_message_failed(
                    payload[:MAX_PARTIAL_MESSAGE_LOG_SIZE], reason, "Malformed HL7 message framing"
                )
            except Exception as e:
                logger.error(f"Failed to log malformed message event: {e}")

        self._send_fallback_nack(reason, ack_builder, self._extract_control_id(payload))

    def _extract_control_id(self, payload: str) -> Optional[str]:
        """Best-effort MSH-10 extraction so the NACK echoes the sender's control ID; None if unavailable."""
        msh_segment = payload.split(self.cr.decode(self.encoding), 1)[0]
        if not msh_segment.startswith("MSH|"):
            return None
        fields = msh_segment.split("|")
        # fields[0] is "MSH", so MSH-10 sits at index 9 (MSH-1 is the separator itself).
        control_id = fields[9].strip() if len(fields) > 9 else ""
        return control_id[:MAX_CONTROL_ID_LENGTH] or None

    def _send_fallback_nack(
        self, reason: str, ack_builder: Optional[HL7AckBuilder], control_id: Optional[str] = None
    ) -> None:
        try:
            builder = ack_builder or HL7AckBuilder()
            nack = builder.build_generic_nack(reason, control_id)
            framed_nack = nack.to_mllp()
            self.wfile.write(framed_nack.encode(self.encoding))
            logger.info(f"Fallback AE NACK ({len(framed_nack)} chars) written to client")
        except Exception as e:
            logger.error(f"Failed to send fallback NACK: {e}")

    def _handle_size_limit_exceeded(
        self,
        accumulated_data: bytes,
        max_message_size: int,
        event_logger: Optional[EventLogger],
        ack_builder: Optional[HL7AckBuilder] = None,
    ) -> None:
        error_msg = (
            f"Message size ({len(accumulated_data)} bytes) "
            f"exceeds maximum allowed size ({max_message_size} bytes). "
            "An AE NACK will be returned and the connection closed."
        )
        logger.error(error_msg)

        if event_logger:
            try:
                partial_message = accumulated_data[:MAX_PARTIAL_MESSAGE_LOG_SIZE].decode('utf-8', errors='ignore')
                event_logger.log_message_failed(
                    partial_message,
                    error_msg,
                    "Message size limit exceeded"
                )
            except Exception:
                pass

        # The buffer is deliberately never parsed here (that's the point of the size guard), so
        # there's no original message to echo - always build a generic AE NACK with a fresh control ID.
        self._send_fallback_nack(error_msg, ack_builder)
        self.request.close()
