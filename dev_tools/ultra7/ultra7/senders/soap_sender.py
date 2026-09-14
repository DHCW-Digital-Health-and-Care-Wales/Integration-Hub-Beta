"""SOAP sender — wraps a message body in a SOAP envelope and POSTs it with a SOAPAction header."""
from __future__ import annotations

from ultra7.models import Endpoint, Message
from ultra7.senders.base import SendResult
from ultra7.senders.http_sender import HttpSender

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


class SoapSender(HttpSender):
    """Sends a message as a SOAP request over HTTP POST."""

    def send(self, endpoint: Endpoint, message: Message) -> SendResult:
        validation_error = self._validate_url(endpoint)
        if validation_error is not None:
            return validation_error

        envelope = _wrap_in_envelope(message.content)
        headers = dict(endpoint.headers)
        headers.setdefault("Content-Type", "text/xml; charset=utf-8")
        if endpoint.soap_action:
            headers.setdefault("SOAPAction", endpoint.soap_action)
        return self._send_http(endpoint, envelope.encode("utf-8"), headers)
