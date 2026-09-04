"""Error types raised by the ``hl7`` pipeline (distinct from ``rest_server.errors``, which is
used by the ``generic`` pipeline only)."""


class Hl7ProcessingError(Exception):
    """Base class for HL7 processing failures raised by the message processor."""


class Hl7ValidationError(Hl7ProcessingError):
    """Raised when a parsed message fails validation.

    Carries the fully-built HL7 NACK string to return to the caller (HTTP 422).
    """

    def __init__(self, nack_message: str, reason: str) -> None:
        super().__init__(reason)
        self.nack_message = nack_message
        self.reason = reason


class Hl7ParseError(Hl7ProcessingError):
    """Raised when the inbound message cannot be parsed at all (HTTP 500)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
