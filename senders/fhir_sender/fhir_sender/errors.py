"""Delivery failure categories raised by the FHIR sender client.

The application maps each category to a Service Bus outcome:
  - PermanentDeliveryError      -> dead-letter (retrying cannot help)
  - AuthorizationDeliveryError  -> alert, abandon (fix credentials, then redrive)
  - TransientDeliveryError      -> abandon (retries already exhausted in the client)
"""
from __future__ import annotations


class DeliveryError(Exception):
    """Base class for all delivery failures."""


class PermanentDeliveryError(DeliveryError):
    """Promptly rejected the message (e.g. 400, 404, 409) or reported an error OperationOutcome."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(f"HTTP {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


class AuthorizationDeliveryError(DeliveryError):
    """Credentials were rejected (401/403) or a token could not be obtained."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(f"HTTP {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


class TransientDeliveryError(DeliveryError):
    """Delivery could not be confirmed (network, 429/5xx, or polling timeout) after all attempts."""
