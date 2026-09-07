"""Helpers for reading queue messages from Azure Service Bus."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from azure.servicebus import NEXT_AVAILABLE_SESSION, ServiceBusClient, ServiceBusMessage

# Queue list refreshes should be responsive in the browser even when a session
# queue is empty, so we use a short wait when probing next available session.
LIST_SESSION_WAIT_SECONDS = 0.2
# Queue clear should drain promptly while still allowing empty queues to return.
CLEAR_SESSION_WAIT_SECONDS = 0.2
# Message detail lookups can afford a slightly longer wait for reliability.
DETAIL_SESSION_WAIT_SECONDS = 1.0
# Clear queue in small batches so the UI remains responsive for larger drains.
CLEAR_BATCH_SIZE = 50


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
    """Read-only wrapper around Azure Service Bus clients.

    This class centralizes queue browsing behavior so route handlers stay
    focused on HTTP concerns. It intentionally supports emulator-first flows,
    including queue discovery from local emulator configuration.
    """

    def __init__(self, connection_string: str) -> None:
        # Session queue names are resolved once at startup from emulator config.
        # These names decide whether to use session-aware or regular receivers.
        self._session_queues: frozenset[str] = _load_emulator_session_queues()
        # Single shared client so all receivers reuse one AMQP connection.
        # Disable retries to keep queue refresh latency predictable in local emulator mode.
        self._client = ServiceBusClient.from_connection_string(connection_string, retry_total=0)

    def close(self) -> None:
        """Release the underlying AMQP connection."""
        self._client.close()

    def list_queues(self) -> list[str]:
        """Return queue names from local emulator configuration."""
        queue_names = _load_emulator_queue_names()
        if not queue_names:
            # Explicit guidance helps users self-diagnose missing config quickly.
            raise RuntimeError(
                "No queues found in local ServiceBusEmulatorConfig.json. "
                "Set BUSWATCH_QUEUE_NAMES or check local emulator configuration."
            )

        return queue_names

    def get_queue_runtime(self, queue_name: str) -> QueueRuntime:
        """Return queue metrics placeholder values for emulator mode."""
        return QueueRuntime(
            name=queue_name,
            active_count=None,
            dead_letter_count=None,
            scheduled_count=None,
            transfer_dead_letter_count=None,
        )

    def peek_messages(self, queue_name: str, max_count: int) -> list[MessageSummary]:
        """Peek messages in a queue without locking or dequeuing."""
        if queue_name in self._session_queues:
            # Session-enabled queues require a session receiver.
            return self._peek_session_queue(queue_name, max_count)

        # Non-session queues can be read with a standard receiver.
        receiver = self._client.get_queue_receiver(queue_name=queue_name)
        with receiver:
            messages = receiver.peek_messages(max_message_count=max_count)

        return [self._to_summary(queue_name, message) for message in messages]

    def clear_queue(self, queue_name: str) -> int:
        """Receive and complete all available messages in a queue."""
        if queue_name in self._session_queues:
            return self._clear_session_queue(queue_name)

        try:
            receiver = self._client.get_queue_receiver(queue_name=queue_name)
            with receiver:
                return self._drain_receiver(receiver)
        except Exception as exc:
            if _is_session_required_error(exc):
                return self._clear_session_queue(queue_name)
            raise

    def _peek_session_queue(self, queue_name: str, max_count: int) -> list[MessageSummary]:
        """Peek messages from the next available session on a session-enabled queue."""
        try:
            receiver = self._client.get_queue_receiver(
                queue_name=queue_name,
                session_id=NEXT_AVAILABLE_SESSION,
                max_wait_time=LIST_SESSION_WAIT_SECONDS,
            )
            with receiver:
                messages = receiver.peek_messages(max_message_count=max_count)
        except Exception as exc:
            # No active session available right now; return empty result.
            # For list pages this is normal when queue has no active session.
            if _is_no_session_available_error(exc):
                return []
            raise

        return [self._to_summary(queue_name, message) for message in messages]

    def _clear_session_queue(self, queue_name: str) -> int:
        """Receive and complete all messages across available sessions."""
        cleared_count = 0

        while True:
            try:
                receiver = self._client.get_queue_receiver(
                    queue_name=queue_name,
                    session_id=NEXT_AVAILABLE_SESSION,
                    max_wait_time=CLEAR_SESSION_WAIT_SECONDS,
                )
            except Exception as exc:
                if _is_no_session_available_error(exc):
                    return cleared_count
                raise

            with receiver:
                session_count = self._drain_receiver(receiver)

            if session_count == 0:
                return cleared_count

            cleared_count += session_count

    def get_message_detail(self, queue_name: str, sequence_number: int, search_limit: int) -> MessageDetail | None:
        """Find one message by sequence number using a bounded peek."""
        if queue_name in self._session_queues:
            # Session queues can only peek within the currently available session.
            messages_summary = self._peek_session_queue(queue_name, search_limit)
            # Re-peek with detail by converting summaries — session queues only surface messages
            # from the next available session; peek detail within that same window.
            for summary in messages_summary:
                if summary.sequence_number == sequence_number:
                    return self._sequence_to_detail(queue_name, sequence_number, search_limit)
            return None

        receiver = self._client.get_queue_receiver(queue_name=queue_name)
        with receiver:
            messages = receiver.peek_messages(max_message_count=search_limit)

        for message in messages:
            if int(getattr(message, "sequence_number", -1)) == sequence_number:
                return self._to_detail(queue_name, message)

        return None

    def _sequence_to_detail(self, queue_name: str, sequence_number: int, search_limit: int) -> MessageDetail | None:
        """Fetch a single message detail from the next available session."""
        try:
            receiver = self._client.get_queue_receiver(
                queue_name=queue_name,
                session_id=NEXT_AVAILABLE_SESSION,
                max_wait_time=DETAIL_SESSION_WAIT_SECONDS,
            )
            with receiver:
                messages = receiver.peek_messages(max_message_count=search_limit)
        except Exception:
            # Surface as not-found semantics to caller when session is unavailable.
            return None

        for message in messages:
            if int(getattr(message, "sequence_number", -1)) == sequence_number:
                return self._to_detail(queue_name, message)

        return None

    def _drain_receiver(self, receiver: Any) -> int:
        """Receive messages in batches until the receiver is empty."""
        cleared_count = 0

        while True:
            messages = receiver.receive_messages(
                max_message_count=CLEAR_BATCH_SIZE,
                max_wait_time=LIST_SESSION_WAIT_SECONDS,
            )
            if not messages:
                return cleared_count

            for message in messages:
                receiver.complete_message(message)
                cleared_count += 1

    def _to_summary(self, queue_name: str, message: ServiceBusMessage) -> MessageSummary:
        """Project a raw Service Bus message into a compact list-row model."""
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
        """Project a raw Service Bus message into a detailed view model."""
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
            # Azure SDK body is iterable and may contain one or more byte chunks.
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
                # Some transports expose memoryview-like chunks.
                raw += bytes(chunk)

        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            # Preserve visibility for binary payloads in a text-centric UI.
            return f"<binary body base64={base64.b64encode(raw).decode('ascii')}>"


def _serialize_application_properties(value: Any) -> dict[str, str]:
    """Normalize application properties to a JSON-template-friendly dict."""
    if not value:
        return {}

    result: dict[str, str] = {}
    for key, prop_value in dict(value).items():
        key_text = _safe_key(key)
        result[key_text] = _stringify_value(prop_value)

    return result


def _safe_key(value: Any) -> str:
    """Convert property keys to stable text for template rendering."""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _safe_str(value: Any) -> str | None:
    """Convert arbitrary scalar values to text while preserving None."""
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _safe_int(value: Any) -> int | None:
    """Best-effort integer conversion for SDK fields that may be absent."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _stringify_value(value: Any) -> str:
    """Convert nested or binary property values to readable text."""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")

    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, default=str)

    return str(value)


def _is_no_session_available_error(exc: Exception) -> bool:
    """Best-effort detection for empty session queues in emulator mode."""
    message = str(exc).lower()
    return "session" in message and "available" in message


def _is_session_required_error(exc: Exception) -> bool:
    """Detect SDK errors that indicate a queue requires a session receiver."""
    message = str(exc).lower()
    return "next_available_session" in message and "max_wait_time" in message


def _load_emulator_session_queues() -> frozenset[str]:
    """Return the names of queues that have RequiresSession enabled in the emulator config."""
    # Multiple candidates are checked so the app works in source, package,
    # and Docker layouts without extra path configuration.
    for candidate in _emulator_config_candidates():
        if not candidate.exists():
            continue

        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            continue

        session_queues = _extract_session_queue_names(payload)
        if _extract_queue_names(payload):  # Only trust config if it has queues at all.
            return frozenset(session_queues)

    return frozenset()


def _extract_session_queue_names(payload: dict[str, object]) -> list[str]:
    """Extract queue names with RequiresSession=true from emulator payload."""
    user_config = payload.get("UserConfig")
    if not isinstance(user_config, dict):
        return []

    namespaces = user_config.get("Namespaces")
    if not isinstance(namespaces, list):
        return []

    names: list[str] = []
    for namespace in namespaces:
        if not isinstance(namespace, dict):
            continue

        queues = namespace.get("Queues")
        if not isinstance(queues, list):
            continue

        for queue in queues:
            if not isinstance(queue, dict):
                continue

            properties = queue.get("Properties")
            requires_session = isinstance(properties, dict) and properties.get("RequiresSession") is True

            queue_name = queue.get("Name")
            if requires_session and isinstance(queue_name, str) and queue_name:
                names.append(queue_name)

    return names


def _load_emulator_queue_names() -> list[str]:
    """Load all queue names from first valid emulator config candidate."""
    for candidate in _emulator_config_candidates():
        if not candidate.exists():
            continue

        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            continue

        queue_names = _extract_queue_names(payload)
        if queue_names:
            return queue_names

    return []


def _emulator_config_candidates() -> list[Path]:
    """Return possible locations of ServiceBusEmulatorConfig.json.

    Candidate order prefers repository-local paths while still supporting
    containerized runs where the config may be mounted next to the app.
    """
    module_dir = Path(__file__).resolve().parent
    return [
        module_dir.parents[1] / "local" / "ServiceBusEmulatorConfig.json",
        module_dir.parent / "ServiceBusEmulatorConfig.json",
        Path.cwd() / "local" / "ServiceBusEmulatorConfig.json",
        Path.cwd() / "ServiceBusEmulatorConfig.json",
    ]


def _extract_queue_names(payload: dict[str, object]) -> list[str]:
    """Extract de-duplicated queue names from emulator JSON payload."""
    user_config = payload.get("UserConfig")
    if not isinstance(user_config, dict):
        return []

    namespaces = user_config.get("Namespaces")
    if not isinstance(namespaces, list):
        return []

    names: list[str] = []
    seen: set[str] = set()

    for namespace in namespaces:
        if not isinstance(namespace, dict):
            continue

        queues = namespace.get("Queues")
        if not isinstance(queues, list):
            continue

        for queue in queues:
            if not isinstance(queue, dict):
                continue

            queue_name = queue.get("Name")
            if isinstance(queue_name, str) and queue_name and queue_name not in seen:
                seen.add(queue_name)
                names.append(queue_name)

    return names
