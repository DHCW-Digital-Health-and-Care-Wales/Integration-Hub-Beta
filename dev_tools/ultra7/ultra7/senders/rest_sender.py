"""REST (HTTP) sender — POSTs a message body to a configured URL."""
from __future__ import annotations

from ultra7.models import Endpoint, Message
from ultra7.senders.base import SendResult
from ultra7.senders.http_sender import HttpSender

_CONTENT_TYPES = {
    "hl7": "application/hl7-v2",
    "xml": "application/xml",
    "json": "application/json",
}


class RestSender(HttpSender):
    """Sends a message as an HTTP POST body."""

    def send(self, endpoint: Endpoint, message: Message) -> SendResult:
        validation_error = self._validate_url(endpoint)
        if validation_error is not None:
            return validation_error

        headers = dict(endpoint.headers)
        headers.setdefault("Content-Type", _CONTENT_TYPES.get(message.format, "text/plain"))
        return self._send_http(endpoint, message.content.encode("utf-8"), headers)
