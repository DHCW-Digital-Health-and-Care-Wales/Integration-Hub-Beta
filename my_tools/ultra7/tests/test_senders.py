import http.server
import socket
import threading
import unittest
from typing import Callable

from ultra7.models import Endpoint, Message
from ultra7.senders.mllp_sender import MLLP_END_BLOCK, MLLP_START_BLOCK, MllpSender
from ultra7.senders.rest_sender import RestSender
from ultra7.senders.soap_sender import SoapSender


def _start_mllp_server(
    ack: bytes | None, received: list[bytes] | None = None
) -> tuple[socket.socket, int]:
    """A minimal MLLP server that reads one framed message and replies with a canned ACK.

    Pass `ack=None` to have the server close the connection without sending anything
    (simulating a server that never acknowledges).
    """
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    def handle() -> None:
        conn, _ = server.accept()
        with conn:
            buffer = b""
            while MLLP_END_BLOCK not in buffer:
                chunk = conn.recv(4096)
                if not chunk:
                    return
                buffer += chunk
            if received is not None:
                received.append(buffer)
            if ack is not None:
                conn.sendall(ack)

    threading.Thread(target=handle, daemon=True).start()
    return server, port


def _start_mllp_echo_server() -> tuple[socket.socket, int]:
    return _start_mllp_server(ack=MLLP_START_BLOCK + b"MSA|AA|MSG1" + MLLP_END_BLOCK + b"\r")


class TestMllpSender(unittest.TestCase):
    def test_send_receives_ack(self) -> None:
        server, port = _start_mllp_echo_server()
        try:
            endpoint = Endpoint(kind="mllp", host="127.0.0.1", port=port, timeout_seconds=2.0)
            message = Message(name="A01", format="hl7", content="MSH|^~\\&|A|B|C|D|20250101||ADT^A01|1|P|2.5")
            result = MllpSender().send(endpoint, message)
            self.assertTrue(result.ok)
            self.assertIn("MSA|AA|MSG1", result.response_summary)
        finally:
            server.close()

    def test_send_normalizes_lf_segment_separators_to_cr(self) -> None:
        received: list[bytes] = []
        ack = MLLP_START_BLOCK + b"MSA|AA|1" + MLLP_END_BLOCK + b"\r"
        server, port = _start_mllp_server(ack=ack, received=received)
        try:
            endpoint = Endpoint(kind="mllp", host="127.0.0.1", port=port, timeout_seconds=2.0)
            message = Message(name="A01", format="hl7", content="MSH|^~\\&|A|B|C|D|20250101||ADT^A01|1|P|2.5\nPID|1")
            result = MllpSender().send(endpoint, message)
            self.assertTrue(result.ok)
            sent = received[0]
            self.assertNotIn(b"\n", sent)
            self.assertIn(b"MSH|^~\\&|A|B|C|D|20250101||ADT^A01|1|P|2.5\rPID|1", sent)
        finally:
            server.close()

    def test_nak_response_is_reported_as_failure(self) -> None:
        server, port = _start_mllp_server(ack=MLLP_START_BLOCK + b"MSA|AE|1" + MLLP_END_BLOCK + b"\r")
        try:
            endpoint = Endpoint(kind="mllp", host="127.0.0.1", port=port, timeout_seconds=2.0)
            message = Message(name="A01", format="hl7", content="MSH|^~\\&|A|B|C|D|20250101||ADT^A01|1|P|2.5")
            result = MllpSender().send(endpoint, message)
            self.assertFalse(result.ok)
            self.assertIn("AE", result.error or "")
        finally:
            server.close()

    def test_no_ack_is_reported_as_failure(self) -> None:
        server, port = _start_mllp_server(ack=None)
        try:
            endpoint = Endpoint(kind="mllp", host="127.0.0.1", port=port, timeout_seconds=2.0)
            message = Message(name="A01", format="hl7", content="MSH|^~\\&|A|B|C|D|20250101||ADT^A01|1|P|2.5")
            result = MllpSender().send(endpoint, message)
            self.assertFalse(result.ok)
            self.assertIsNotNone(result.error)
        finally:
            server.close()

    def test_missing_host_port_is_an_error(self) -> None:
        endpoint = Endpoint(kind="mllp")
        message = Message(name="A01", format="hl7", content="MSH|...")
        result = MllpSender().send(endpoint, message)
        self.assertFalse(result.ok)
        self.assertIsNotNone(result.error)

    def test_connection_refused_is_reported_as_error(self) -> None:
        endpoint = Endpoint(kind="mllp", host="127.0.0.1", port=1, timeout_seconds=1.0)
        message = Message(name="A01", format="hl7", content="MSH|...")
        result = MllpSender().send(endpoint, message)
        self.assertFalse(result.ok)


def _make_handler(record: Callable[[http.server.BaseHTTPRequestHandler, bytes], None]) -> type:
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            record(self, body)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ack")

        def log_message(self, *args: object) -> None:  # silence test output
            pass

    return Handler


class TestRestSender(unittest.TestCase):
    def test_rejects_non_http_scheme(self) -> None:
        endpoint = Endpoint(kind="rest", url="file:///etc/passwd")
        message = Message(name="m", format="json", content="{}")
        result = RestSender().send(endpoint, message)
        self.assertFalse(result.ok)
        self.assertIn("scheme", result.error or "")

    def test_missing_url_is_an_error(self) -> None:
        endpoint = Endpoint(kind="rest", url="")
        message = Message(name="m", format="json", content="{}")
        result = RestSender().send(endpoint, message)
        self.assertFalse(result.ok)

    def test_posts_body_and_returns_response(self) -> None:
        received: list[bytes] = []
        handler = _make_handler(lambda _req, body: received.append(body))
        server = http.server.HTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            endpoint = Endpoint(kind="rest", url=f"http://127.0.0.1:{port}/ingest", timeout_seconds=2.0)
            message = Message(name="m", format="json", content='{"a": 1}')
            result = RestSender().send(endpoint, message)
            self.assertTrue(result.ok)
            self.assertIn("HTTP 200", result.response_summary)
            self.assertEqual(received[0], b'{"a": 1}')
        finally:
            server.shutdown()
            server.server_close()


class TestSoapSender(unittest.TestCase):
    def test_wraps_body_in_envelope_and_sets_soap_action(self) -> None:
        received: dict[str, object] = {}

        def record(req: http.server.BaseHTTPRequestHandler, body: bytes) -> None:
            received["body"] = body
            received["soap_action"] = req.headers.get("SOAPAction")

        handler = _make_handler(record)
        server = http.server.HTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            endpoint = Endpoint(
                kind="soap", url=f"http://127.0.0.1:{port}/soap", soap_action="urn:submit", timeout_seconds=2.0
            )
            message = Message(name="m", format="xml", content="<Payload/>")
            result = SoapSender().send(endpoint, message)
            self.assertTrue(result.ok)
            self.assertIn(b"Envelope", received["body"])  # type: ignore[operator]
            self.assertIn(b"<Payload/>", received["body"])  # type: ignore[operator]
            self.assertEqual(received["soap_action"], "urn:submit")
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
