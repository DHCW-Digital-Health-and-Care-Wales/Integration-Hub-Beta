"""Protocol clients for sending Ultra7 test messages (MLLP, REST, SOAP)."""
from __future__ import annotations

from ultra7.models import EndpointKind
from ultra7.senders.base import Sender
from ultra7.senders.mllp_sender import MllpSender
from ultra7.senders.rest_sender import RestSender
from ultra7.senders.soap_sender import SoapSender

_SENDERS_BY_KIND: dict[EndpointKind, Sender] = {
    "mllp": MllpSender(),
    "rest": RestSender(),
    "soap": SoapSender(),
}


def get_sender(kind: EndpointKind) -> Sender:
    try:
        return _SENDERS_BY_KIND[kind]
    except KeyError as exc:
        raise ValueError(f"Unknown endpoint kind: {kind}") from exc
