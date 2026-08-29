"""SOAP sender — wraps a message body in a SOAP envelope and POSTs it with a SOAPAction header."""
from __future__ import annotations

import time
import urllib.error
import urllib.request

from ultra7.models import Endpoint, Message
from ultra7.senders.base import SendResult

_ALLOWED_SCHEMES = {"http", "https"}

_ENVELOPE_TEMPLATE = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
    "<soap:Body>{body}</soap:Body>"
    "</soap:Envelope>"
)


def _wrap_in_envelope(content: str) -> str:
    """Wrap raw content in a SOAP envelope unless it already looks like one."""
    stripped = content.strip()
    if "Envelope" in stripped[:200]:
        return stripped
    return _ENVELOPE_TEMPLATE.format(body=stripped)


class SoapSender:
    """Sends a message as a SOAP request over HTTP POST."""

    def send(self, endpoint: Endpoint, message: Message) -> SendResult:
        if not endpoint.url:
            return SendResult(ok=False, latency_ms=0.0, response_summary="", error="URL is required")

        parsed_scheme = endpoint.url.split("://", 1)[0].lower()
        if parsed_scheme not in _ALLOWED_SCHEMES:
            return SendResult(
                ok=False, latency_ms=0.0, response_summary="", error=f"Unsupported URL scheme: {parsed_scheme}"
            )

        envelope = _wrap_in_envelope(message.content)
        headers = dict(endpoint.headers)
        headers.setdefault("Content-Type", "text/xml; charset=utf-8")
        if endpoint.soap_action:
            headers.setdefault("SOAPAction", endpoint.soap_action)

        request = urllib.request.Request(
            endpoint.url,
            data=envelope.encode("utf-8"),
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
