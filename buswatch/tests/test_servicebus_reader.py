"""Unit tests for ServiceBusReader helpers that do not hit Azure."""

from __future__ import annotations

from typing import Any

from buswatch.servicebus_reader import ServiceBusReader, _serialize_application_properties


class FakeReceiver:
    def __init__(self, batches: list[list[Any]]) -> None:
        self._batches = list(batches)
        self.completed_messages: list[Any] = []

    def __enter__(self) -> "FakeReceiver":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False

    def receive_messages(self, max_message_count: int, max_wait_time: float) -> list[Any]:
        assert max_message_count > 0
        assert max_wait_time >= 0
        if not self._batches:
            return []
        return self._batches.pop(0)

    def complete_message(self, message: Any) -> None:
        self.completed_messages.append(message)


class FakeClient:
    def __init__(self, receivers: list[FakeReceiver | Exception]) -> None:
        self._receivers = list(receivers)
        self.calls: list[dict[str, Any]] = []

    def get_queue_receiver(self, **kwargs: Any) -> FakeReceiver:
        self.calls.append(kwargs)
        next_receiver = self._receivers.pop(0)
        if isinstance(next_receiver, Exception):
            raise next_receiver
        return next_receiver



def test_serialize_application_properties_handles_bytes_keys_and_values() -> None:
    result = _serialize_application_properties({b"k": b"v"})

    assert result == {"k": "v"}



def test_serialize_application_properties_handles_nested_values() -> None:
    result = _serialize_application_properties({"meta": {"count": 2}})

    assert result == {"meta": '{"count": 2}'}


def test_clear_queue_completes_all_messages_for_non_session_queue() -> None:
    reader = ServiceBusReader.__new__(ServiceBusReader)
    receiver = FakeReceiver(batches=[["m1", "m2"], ["m3"], []])
    reader._client = FakeClient([receiver])
    reader._session_queues = frozenset()

    cleared_count = reader.clear_queue("training-hl7-server")

    assert cleared_count == 3
    assert receiver.completed_messages == ["m1", "m2", "m3"]


def test_clear_queue_drains_multiple_sessions_until_none_available() -> None:
    reader = ServiceBusReader.__new__(ServiceBusReader)
    first_session = FakeReceiver(batches=[["m1"], []])
    second_session = FakeReceiver(batches=[["m2", "m3"], []])
    no_session = RuntimeError("No session available for entity")
    client = FakeClient([first_session, second_session, no_session])
    reader._client = client
    reader._session_queues = frozenset({"session-queue"})

    cleared_count = reader.clear_queue("session-queue")

    assert cleared_count == 3
    assert first_session.completed_messages == ["m1"]
    assert second_session.completed_messages == ["m2", "m3"]
    assert all(call["queue_name"] == "session-queue" for call in client.calls)
