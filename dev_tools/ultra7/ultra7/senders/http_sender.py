"""Shared HTTP sender base class for REST and SOAP protocol clients."""
from __future__ import annotations

import time
import urllib.error
import urllib.request

from ultra7.models import Endpoint
from ultra7.senders.base import SendResult

_ALLOWED_SCHEMES = {"http", "https"}


class HttpSender:
    """Base class for HTTP-based senders (REST, SOAP)."""

    def _validate_url(self, endpoint: Endpoint) -> SendResult | None:
        """Validate the endpoint URL. Returns an error SendResult if invalid, None if valid."""
        if not endpoint.url:
            return SendResult(ok=False, latency_ms=0.0, response_summary="", error="URL is required")

        parsed_scheme = endpoint.url.split("://", 1)[0].lower()
        if parsed_scheme not in _ALLOWED_SCHEMES:
            return SendResult(
                ok=False, latency_ms=0.0, response_summary="", error=f"Unsupported URL scheme: {parsed_scheme}"
            )
        return None

    def _send_http(
        self, endpoint: Endpoint, body: bytes, headers: dict[str, str]
    ) -> SendResult:
        """Send an HTTP POST request and return the result."""
        request = urllib.request.Request(
            endpoint.url,
            data=body,
            headers=headers,
            method="POST",
        )

        start = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=endpoint.timeout_seconds) as response:  # noqa: S310
                response_body = response.read().decode("utf-8", errors="replace")
                status = response.status
        except urllib.error.HTTPError as exc:
            latency_ms = (time.monotonic() - start) * 1000
            response_body = exc.read().decode("utf-8", errors="replace")
            return SendResult(ok=False, latency_ms=latency_ms, response_summary=response_body, error=f"HTTP {exc.code}")
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            latency_ms = (time.monotonic() - start) * 1000
            return SendResult(ok=False, latency_ms=latency_ms, response_summary="", error=str(exc))

        latency_ms = (time.monotonic() - start) * 1000
        return SendResult(ok=True, latency_ms=latency_ms, response_summary=f"HTTP {status}: {response_body}")
