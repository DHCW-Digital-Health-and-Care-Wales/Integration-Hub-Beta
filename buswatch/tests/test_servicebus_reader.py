"""Unit tests for ServiceBusReader helpers that do not hit Azure."""

from __future__ import annotations

from buswatch.servicebus_reader import _serialize_application_properties



def test_serialize_application_properties_handles_bytes_keys_and_values() -> None:
    result = _serialize_application_properties({b"k": b"v"})

    assert result == {"k": "v"}



def test_serialize_application_properties_handles_nested_values() -> None:
    result = _serialize_application_properties({"meta": {"count": 2}})

    assert result == {"meta": '{"count": 2}'}
