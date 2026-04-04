"""Helpers for reading queue messages from Azure Service Bus."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from azure.servicebus import ServiceBusClient, ServiceBusMessage
from azure.servicebus.management import ServiceBusAdministrationClient


@dataclass(frozen=True)
class QueueRuntime:
    """Queue status details used by the list view."""

    name: str
    active_count: int | None
    dead_letter_count: int | None
    scheduled_count: int | None
    transfer_dead_letter_count: int | None


@dataclass(frozen=True)
class MessageSummary:
    """Small message projection for queue list pages."""

    queue_name: str
    sequence_number: int | None
    message_id: str | None
    subject: str | None
    enqueued_time_utc: datetime | None
    content_preview: str


@dataclass(frozen=True)
class MessageDetail:
    """Detailed message projection for single-message pages."""

    queue_name: str
    sequence_number: int | None
    message_id: str | None
    correlation_id: str | None
    subject: str | None
    content_type: str | None
    enqueued_time_utc: datetime | None
    body: str
    application_properties: dict[str, str]


class ServiceBusReader:
    """Thin read-only wrapper around Azure Service Bus clients."""

    def __init__(self, connection_string: str) -> None:
        self._connection_string = connection_string

    def list_queues(self) -> list[str]:
        """Return queue names from the namespace."""
        with ServiceBusAdministrationClient.from_connection_string(self._connection_string) as admin_client:
            return sorted(queue.name for queue in admin_client.list_queues())

    def get_queue_runtime(self, queue_name: str) -> QueueRuntime:
        """Return runtime metrics for a queue."""
        with ServiceBusAdministrationClient.from_connection_string(self._connection_string) as admin_client:
            properties = admin_client.get_queue_runtime_properties(queue_name)
            return QueueRuntime(
                name=queue_name,
                active_count=properties.active_message_count,
                dead_letter_count=properties.dead_letter_message_count,
                scheduled_count=properties.scheduled_message_count,
                transfer_dead_letter_count=properties.transfer_dead_letter_message_count,
            )

    def peek_messages(self, queue_name: str, max_count: int) -> list[MessageSummary]:
        """Peek messages in a queue without locking or dequeuing."""
        with ServiceBusClient.from_connection_string(self._connection_string) as client:
            receiver = client.get_queue_receiver(queue_name=queue_name)
            with receiver:
                messages = receiver.peek_messages(max_message_count=max_count)

        return [self._to_summary(queue_name, message) for message in messages]

    def get_message_detail(self, queue_name: str, sequence_number: int, search_limit: int) -> MessageDetail | None:
        """Find one message by sequence number using a bounded peek."""
        with ServiceBusClient.from_connection_string(self._connection_string) as client:
            receiver = client.get_queue_receiver(queue_name=queue_name)
            with receiver:
                messages = receiver.peek_messages(max_message_count=search_limit)

        for message in messages:
            if int(getattr(message, "sequence_number", -1)) == sequence_number:
                return self._to_detail(queue_name, message)

        return None

    def _to_summary(self, queue_name: str, message: ServiceBusMessage) -> MessageSummary:
        body = self._decode_body(message)
        preview = body if len(body) <= 120 else f"{body[:117]}..."

        return MessageSummary(
            queue_name=queue_name,
            sequence_number=_safe_int(getattr(message, "sequence_number", None)),
            message_id=_safe_str(getattr(message, "message_id", None)),
            subject=_safe_str(getattr(message, "subject", None)),
            enqueued_time_utc=getattr(message, "enqueued_time_utc", None),
            content_preview=preview,
        )

    def _to_detail(self, queue_name: str, message: ServiceBusMessage) -> MessageDetail:
        return MessageDetail(
            queue_name=queue_name,
            sequence_number=_safe_int(getattr(message, "sequence_number", None)),
            message_id=_safe_str(getattr(message, "message_id", None)),
            correlation_id=_safe_str(getattr(message, "correlation_id", None)),
            subject=_safe_str(getattr(message, "subject", None)),
            content_type=_safe_str(getattr(message, "content_type", None)),
            enqueued_time_utc=getattr(message, "enqueued_time_utc", None),
            body=self._decode_body(message),
            application_properties=_serialize_application_properties(getattr(message, "application_properties", None)),
        )

    def _decode_body(self, message: ServiceBusMessage) -> str:
        """Decode message body chunks to UTF-8 text where possible."""
        try:
            body_chunks = list(message.body)
        except Exception:
            return "<unable to decode body>"

        if not body_chunks:
            return ""

        raw = b""
        for chunk in body_chunks:
            if isinstance(chunk, bytes):
                raw += chunk
            else:
                raw += bytes(chunk)

        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return f"<binary body base64={base64.b64encode(raw).decode('ascii')}>"


def _serialize_application_properties(value: Any) -> dict[str, str]:
    if not value:
        return {}

    result: dict[str, str] = {}
    for key, prop_value in dict(value).items():
        key_text = _safe_key(key)
        result[key_text] = _stringify_value(prop_value)

    return result


def _safe_key(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _stringify_value(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")

    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, default=str)

    return str(value)
