"""REST (HTTP) sender — POSTs a message body to a configured URL."""
from __future__ import annotations

import time
import urllib.error
import urllib.request

from ultra7.models import Endpoint, Message
from ultra7.senders.base import SendResult

_CONTENT_TYPES = {
    "hl7": "application/hl7-v2",
    "xml": "application/xml",
    "json": "application/json",
}

_ALLOWED_SCHEMES = {"http", "https"}


class RestSender:
    """Sends a message as an HTTP POST body."""

    def send(self, endpoint: Endpoint, message: Message) -> SendResult:
        if not endpoint.url:
            return SendResult(ok=False, latency_ms=0.0, response_summary="", error="URL is required")

        parsed_scheme = endpoint.url.split("://", 1)[0].lower()
        if parsed_scheme not in _ALLOWED_SCHEMES:
            return SendResult(
                ok=False, latency_ms=0.0, response_summary="", error=f"Unsupported URL scheme: {parsed_scheme}"
            )

        headers = dict(endpoint.headers)
        headers.setdefault("Content-Type", _CONTENT_TYPES.get(message.format, "text/plain"))
        request = urllib.request.Request(
            endpoint.url,
            data=message.content.encode("utf-8"),
            headers=headers,
            method="POST",
        )

        start = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=endpoint.timeout_seconds) as response:  # noqa: S310
                body = response.read().decode("utf-8", errors="replace")
                status = response.status
        except urllib.error.HTTPError as exc:
            latency_ms = (time.monotonic() - start) * 1000
            body = exc.read().decode("utf-8", errors="replace")
            return SendResult(ok=False, latency_ms=latency_ms, response_summary=body, error=f"HTTP {exc.code}")
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            latency_ms = (time.monotonic() - start) * 1000
            return SendResult(ok=False, latency_ms=latency_ms, response_summary="", error=str(exc))

        latency_ms = (time.monotonic() - start) * 1000
        return SendResult(ok=True, latency_ms=latency_ms, response_summary=f"HTTP {status}: {body}")
