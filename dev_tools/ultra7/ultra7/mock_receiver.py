"""Lightweight local Mock MLLP and HTTP/SOAP receivers for developer testing."""
from __future__ import annotations

import socket
import socketserver
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Literal

from ultra7.formats.detect import detect_format
from ultra7.models import MessageFormat
from ultra7.senders.mllp_sender import MLLP_END_BLOCK, MLLP_END_SEQ, MLLP_START_BLOCK

ReceiverKind = Literal["mllp", "http"]


@dataclass(frozen=True)
class ReceivedMessage:
    """A single inbound message captured by a local mock receiver."""

    timestamp: str
    protocol: ReceiverKind
    remote: str
    content: str
    detected_format: MessageFormat
    response_sent: str


def build_hl7_ack(raw_hl7: str, ack_code: str = "AA") -> str:
    """Build a minimal HL7 v2.x ACK referencing the incoming MSH-10 control ID."""
    control_id = "0"
    for seg in raw_hl7.replace("\r\n", "\r").replace("\n", "\r").split("\r"):
        if seg.startswith("MSH|"):
            fields = seg.split("|")
            if len(fields) > 9 and fields[9]:
                control_id = fields[9]
            break
    now = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"MSH|^~\\&|ULTRA7|MOCK|SENDER|APP|{now}||ACK|{control_id}|P|2.5\rMSA|{ack_code}|{control_id}\r"


class _ReusableTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class MockMllpServer:
    """Threaded TCP server that accepts MLLP-framed HL7 messages and returns configurable ACKs."""

    def __init__(
        self,
        host: str,
        port: int,
        ack_code: str = "AA",
        delay_ms: int = 0,
        on_message: Callable[[ReceivedMessage], None] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.ack_code = ack_code
        self.delay_ms = max(0, delay_ms)
        self._on_message = on_message
        self._server: _ReusableTCPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> int:
        """Start listening in a daemon thread. Returns the bound port."""
        parent = self

        class _Handler(socketserver.BaseRequestHandler):
            def handle(self) -> None:
                sock: socket.socket = self.request
                sock.settimeout(5.0)
                buf = b""
                remote = f"{self.client_address[0]}:{self.client_address[1]}"

                # Loop on the persistent TCP connection to handle a stream of MLLP frames,
                # matching servers/hl7_server's SizeLimitedMLLPRequestHandler behaviour.
                while True:
                    buf = buf.lstrip(b"\r\n")
                    while not buf:
                        try:
                            chunk = sock.recv(4096)
                        except (OSError, TimeoutError):
                            return
                        if not chunk:
                            return
                        buf = chunk.lstrip(b"\r\n")

                    while MLLP_END_SEQ not in buf:
                        if MLLP_END_BLOCK in buf:
                            idx = buf.find(MLLP_END_BLOCK)
                            if idx + 1 < len(buf) and buf[idx + 1 : idx + 2] != b"\r":
                                break
                        try:
                            chunk = sock.recv(4096)
                        except (OSError, TimeoutError):
                            return
                        if not chunk:
                            break
                        buf += chunk

                    if MLLP_END_SEQ in buf:
                        end_pos = buf.find(MLLP_END_SEQ) + len(MLLP_END_SEQ)
                    elif MLLP_END_BLOCK in buf:
                        end_pos = buf.find(MLLP_END_BLOCK) + len(MLLP_END_BLOCK)
                    else:
                        return

                    frame_bytes = buf[:end_pos]
                    buf = buf[end_pos:]

                    raw = frame_bytes.decode("utf-8", errors="replace").strip("\x0b\x1c\r\n")
                    if parent.delay_ms:
                        time.sleep(parent.delay_ms / 1000)
                    ack = build_hl7_ack(raw, parent.ack_code)
                    reply_frame = MLLP_START_BLOCK + ack.encode("utf-8") + MLLP_END_SEQ
                    send_ok = True
                    try:
                        sock.sendall(reply_frame)
                    except OSError:
                        send_ok = False
                    if parent._on_message is not None:
                        ts = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
                        parent._on_message(
                            ReceivedMessage(
                                timestamp=ts,
                                protocol="mllp",
                                remote=remote,
                                content=raw,
                                detected_format=detect_format(raw),
                                response_sent=ack,
                            )
                        )
                    if not send_ok:
                        return

        self._server = _ReusableTCPServer((self.host, self.port), _Handler)
        self.port = int(self._server.server_address[1])
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self.port

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None


class MockHttpServer:
    """Threaded HTTP server for testing REST/SOAP senders locally."""

    def __init__(
        self,
        host: str,
        port: int,
        status_code: int = 200,
        response_body: str = '{"status": "ok"}',
        content_type: str = "application/json",
        delay_ms: int = 0,
        on_message: Callable[[ReceivedMessage], None] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.status_code = status_code
        self.response_body = response_body
        self.content_type = content_type
        self.delay_ms = max(0, delay_ms)
        self._on_message = on_message
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> int:
        parent = self

        class _Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0") or "0")
                raw_bytes = self.rfile.read(length) if length > 0 else b""
                body = raw_bytes.decode("utf-8", errors="replace")
                if parent.delay_ms:
                    time.sleep(parent.delay_ms / 1000)
                payload = parent.response_body.encode("utf-8")
                try:
                    self.send_response(parent.status_code)
                    self.send_header("Content-Type", parent.content_type)
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                except OSError:
                    pass
                if parent._on_message is not None:
                    remote = f"{self.client_address[0]}:{self.client_address[1]}"
                    ts = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
                    parent._on_message(
                        ReceivedMessage(
                            timestamp=ts,
                            protocol="http",
                            remote=remote,
                            content=body,
                            detected_format=detect_format(body),
                            response_sent=f"HTTP {parent.status_code}: {parent.response_body}",
                        )
                    )

            def do_HEAD(self) -> None:  # noqa: N802
                self.send_response(parent.status_code)
                self.end_headers()

            def log_message(self, _format: str, *_args: object) -> None:
                return

        self._server = ThreadingHTTPServer((self.host, self.port), _Handler)
        self.port = int(self._server.server_address[1])
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self.port

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
