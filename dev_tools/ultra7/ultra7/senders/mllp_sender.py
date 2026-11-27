"""MLLP (TCP) sender — supports per-message, persistent stream, and pipelined burst modes."""
from __future__ import annotations

import socket
import time
from types import TracebackType

from ultra7.models import Endpoint, Message
from ultra7.senders.base import SendResult

MLLP_START_BLOCK = b"\x0b"
MLLP_END_BLOCK = b"\x1c"
MLLP_CARRIAGE_RETURN = b"\r"
MLLP_END_SEQ = MLLP_END_BLOCK + MLLP_CARRIAGE_RETURN

_READ_CHUNK_SIZE = 4096


# HL7 segments must be separated by CR (\r), not LF. Messages typed/pasted/loaded
# from disk in this tool commonly use \n or \r\n line endings and trailing newlines,
# which hl7_server rejects as empty segments — normalize and strip leading/trailing
# terminators before framing.
def _to_er7(content: str) -> str:
    return content.replace("\r\n", "\r").replace("\n", "\r").strip("\r")


def frame_mllp(content: str) -> bytes:
    """Wrap an HL7 message in MLLP framing bytes (<VT>payload<FS><CR>)."""
    payload = _to_er7(content).encode("utf-8")
    return MLLP_START_BLOCK + payload + MLLP_END_SEQ


def _extract_ack_code(ack_text: str) -> str | None:
    """Pull the MSA-1 acknowledgement code (AA/AE/AR/...) out of an ACK, if present."""
    for segment in ack_text.replace("\n", "\r").split("\r"):
        if segment.startswith("MSA|"):
            fields = segment.split("|")
            if len(fields) > 1 and fields[1]:
                return fields[1]
    return None


def _parse_ack_result(raw_frame: bytes, latency_ms: float) -> SendResult:
    text = raw_frame.decode("utf-8", errors="replace").strip("\x0b\x1c\r\n")
    if not text:
        return SendResult(
            ok=False, latency_ms=latency_ms, response_summary="", error="No ACK received (connection closed)"
        )
    ack_code = _extract_ack_code(text)
    if ack_code is not None and ack_code not in ("AA", "CA"):
        return SendResult(ok=False, latency_ms=latency_ms, response_summary=text, error=f"NAK: {ack_code}")
    return SendResult(ok=True, latency_ms=latency_ms, response_summary=text)


class MllpStreamSession:
    """Persistent TCP connection for streaming or pipelining multiple MLLP frames.

    Compatible with ``servers/hl7_server``'s ``SizeLimitedMLLPRequestHandler`` which
    reads multiple MLLP frames over a single TCP socket until client EOF or idle timeout.
    """

    def __init__(self, endpoint: Endpoint) -> None:
        self._endpoint = endpoint
        self._sock: socket.socket | None = None
        self._recv_buffer = b""

    def __enter__(self) -> MllpStreamSession:
        self.connect()
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _tb: TracebackType | None,
    ) -> None:
        self.close()

    def connect(self) -> None:
        if self._sock is not None:
            return
        if not self._endpoint.host or not self._endpoint.port:
            raise OSError("Host and port are required")
        sock = socket.create_connection(
            (self._endpoint.host, self._endpoint.port),
            timeout=self._endpoint.timeout_seconds,
        )
        sock.settimeout(self._endpoint.timeout_seconds)
        self._sock = sock
        self._recv_buffer = b""

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        self._recv_buffer = b""

    def send_frame(self, message: Message) -> None:
        """Write a single MLLP frame onto the stream without reading its ACK yet."""
        if self._sock is None:
            self.connect()
        if self._sock is None:
            raise OSError("Stream is not connected")
        self._sock.sendall(frame_mllp(message.content))

    def read_next_ack(self, start_time: float | None = None) -> SendResult:
        """Read exactly one MLLP-framed ACK from the stream, retaining any trailing bytes."""
        start = start_time if start_time is not None else time.monotonic()
        if self._sock is None:
            return SendResult(ok=False, latency_ms=0.0, response_summary="", error="Stream is not connected")
        try:
            raw_frame = self._read_ack_frame()
        except (OSError, TimeoutError) as exc:
            self.close()
            return SendResult(
                ok=False, latency_ms=(time.monotonic() - start) * 1000, response_summary="", error=str(exc)
            )
        latency_ms = (time.monotonic() - start) * 1000
        if not raw_frame:
            self.close()
        return _parse_ack_result(raw_frame, latency_ms)

    def send_message(self, message: Message) -> SendResult:
        """Send one MLLP frame on the persistent stream and wait for its ACK."""
        start = time.monotonic()
        try:
            if self._sock is None:
                self.connect()
            self.send_frame(message)
        except (OSError, TimeoutError) as exc:
            self.close()
            return SendResult(
                ok=False, latency_ms=(time.monotonic() - start) * 1000, response_summary="", error=str(exc)
            )
        return self.read_next_ack(start_time=start)

    def _read_ack_frame(self) -> bytes:
        if self._sock is None:
            raise OSError("Stream is not connected")
        self._recv_buffer = self._recv_buffer.lstrip(b"\r\n")
        while MLLP_END_SEQ not in self._recv_buffer:
            if MLLP_END_BLOCK in self._recv_buffer:
                # Server might omit the trailing CR after 0x1C; check if next byte arrives or EOF.
                idx = self._recv_buffer.find(MLLP_END_BLOCK)
                if idx + 1 < len(self._recv_buffer):
                    frame = self._recv_buffer[: idx + 1]
                    self._recv_buffer = self._recv_buffer[idx + 1 :]
                    return frame
            chunk = self._sock.recv(_READ_CHUNK_SIZE)
            if not chunk:
                frame = self._recv_buffer
                self._recv_buffer = b""
                return frame
            self._recv_buffer += chunk

        end_pos = self._recv_buffer.find(MLLP_END_SEQ) + len(MLLP_END_SEQ)
        frame = self._recv_buffer[:end_pos]
        self._recv_buffer = self._recv_buffer[end_pos:]
        return frame


class MllpSender:
    """Sends a message over a plain TCP socket using MLLP framing."""

    def open_stream(self, endpoint: Endpoint) -> MllpStreamSession:
        return MllpStreamSession(endpoint)

    def send(self, endpoint: Endpoint, message: Message) -> SendResult:
        if not endpoint.host or not endpoint.port:
            return SendResult(ok=False, latency_ms=0.0, response_summary="", error="Host and port are required")

        frame = frame_mllp(message.content)

        start = time.monotonic()
        try:
            with socket.create_connection((endpoint.host, endpoint.port), timeout=endpoint.timeout_seconds) as sock:
                sock.sendall(frame)
                sock.settimeout(endpoint.timeout_seconds)
                response = self._read_ack(sock)
        except (OSError, TimeoutError) as exc:
            latency_ms = (time.monotonic() - start) * 1000
            return SendResult(ok=False, latency_ms=latency_ms, response_summary="", error=str(exc))

        latency_ms = (time.monotonic() - start) * 1000
        return _parse_ack_result(response, latency_ms)

    def _read_ack(self, sock: socket.socket) -> bytes:
        """Read from the socket until the MLLP end block (or the socket times out)."""
        buffer = b""
        while MLLP_END_BLOCK not in buffer:
            chunk = sock.recv(_READ_CHUNK_SIZE)
            if not chunk:
                break
            buffer += chunk
        return buffer

    def _extract_ack_code(self, ack_text: str) -> str | None:
        """Pull the MSA-1 acknowledgement code (AA/AE/AR/...) out of an ACK, if present."""
        return _extract_ack_code(ack_text)
