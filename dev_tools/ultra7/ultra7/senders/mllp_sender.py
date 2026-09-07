"""MLLP (TCP) sender — wraps a message in HL7 MLLP framing and sends it over a socket."""
from __future__ import annotations

import socket
import time

from ultra7.models import Endpoint, Message
from ultra7.senders.base import SendResult

MLLP_START_BLOCK = b"\x0b"
MLLP_END_BLOCK = b"\x1c"
MLLP_CARRIAGE_RETURN = b"\r"

_READ_CHUNK_SIZE = 4096

# HL7 segments must be separated by CR (\r), not LF. Messages typed/pasted/loaded
# from disk in this tool commonly use \n or \r\n line endings, which most HL7
# receivers (including hl7apy-based servers) will fail to parse — normalize
# before sending, the same way `mllp_send --loose` does.
def _to_er7(content: str) -> str:
    return content.replace("\r\n", "\r").replace("\n", "\r")


class MllpSender:
    """Sends a message over a plain TCP socket using MLLP framing."""

    def send(self, endpoint: Endpoint, message: Message) -> SendResult:
        if not endpoint.host or not endpoint.port:
            return SendResult(ok=False, latency_ms=0.0, response_summary="", error="Host and port are required")

        payload = _to_er7(message.content).encode("utf-8")
        frame = MLLP_START_BLOCK + payload + MLLP_END_BLOCK + MLLP_CARRIAGE_RETURN

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
        text = response.decode("utf-8", errors="replace").strip("\x0b\x1c\r\n")

        if not text:
            return SendResult(
                ok=False, latency_ms=latency_ms, response_summary="", error="No ACK received (connection closed)"
            )

        ack_code = self._extract_ack_code(text)
        if ack_code is not None and ack_code not in ("AA", "CA"):
            return SendResult(ok=False, latency_ms=latency_ms, response_summary=text, error=f"NAK: {ack_code}")

        return SendResult(ok=True, latency_ms=latency_ms, response_summary=text)

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
        for segment in ack_text.replace("\n", "\r").split("\r"):
            if segment.startswith("MSA|"):
                fields = segment.split("|")
                if len(fields) > 1 and fields[1]:
                    return fields[1]
        return None
