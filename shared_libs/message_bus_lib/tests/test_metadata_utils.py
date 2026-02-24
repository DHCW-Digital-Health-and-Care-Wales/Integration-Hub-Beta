import unittest
import uuid
from typing import Any
from unittest.mock import MagicMock

from message_bus_lib.metadata_utils import (
    CORRELATION_ID_KEY,
    MESSAGE_RECEIVED_AT_KEY,
    SOURCE_SYSTEM_KEY,
    WORKFLOW_ID_KEY,
    correlation_id_for_logger,
    extract_metadata,
    get_metadata_log_values,
)


def _message_with_properties(props: dict[Any, Any] | None) -> MagicMock:
    message = MagicMock()
    message.application_properties = props
    return message


class TestExtractMetadata(unittest.TestCase):
    def test_returns_none_when_no_or_empty_properties(self) -> None:
        props: dict[str, Any] | None
        for props in (None, {}):
            with self.subTest(props=props):
                message = _message_with_properties(props)
                self.assertIsNone(extract_metadata(message))

    def test_primitive_type_values_converted_to_str(self) -> None:
        u = uuid.uuid4()
        cases: list[tuple[dict[Any, Any], dict[str, str]]] = [
            ({"key": "evt-123"}, {"key": "evt-123"}),
            ({b"CorrelationId": b"evt-456"}, {"CorrelationId": "evt-456"}),
            ({"Count": 42}, {"Count": "42"}),
            ({"Score": 3.14}, {"Score": "3.14"}),
            ({"Flag": True}, {"Flag": "True"}),
            ({"Id": u}, {"Id": str(u)}),
        ]
        for props, expected in cases:
            with self.subTest(props=props):
                message = _message_with_properties(props)
                self.assertEqual(extract_metadata(message), expected)

    def test_mixed_primitive_types(self) -> None:
        u = uuid.uuid4()
        message = _message_with_properties(
            {
                "str_key": "s",
                b"bytes_key": b"b",
                "int_val": 1,
                "float_val": 1.0,
                "bool_val": False,
                "uuid_val": u,
            }
        )
        result = extract_metadata(message)
        expected = {
            "str_key": "s",
            "bytes_key": "b",
            "int_val": "1",
            "float_val": "1.0",
            "bool_val": "False",
            "uuid_val": str(u),
        }
        self.assertEqual(result, expected)


class TestGetMetadataLogValues(unittest.TestCase):
    _NA_DEFAULTS = {
        "correlation_id": "N/A",
        "workflow_id": "N/A",
        "source_system": "N/A",
        "message_received_at": "N/A",
    }

    def test_none_or_empty_returns_na_defaults(self) -> None:
        metadata: dict[str, Any] | None
        for metadata in (None, {}):
            with self.subTest(metadata=metadata):
                self.assertEqual(get_metadata_log_values(metadata), self._NA_DEFAULTS)

    def test_populated_metadata(self) -> None:
        meta = {
            CORRELATION_ID_KEY: "e1",
            WORKFLOW_ID_KEY: "w1",
            SOURCE_SYSTEM_KEY: "src",
            MESSAGE_RECEIVED_AT_KEY: "2025-01-01T00:00:00",
        }
        self.assertEqual(
            get_metadata_log_values(meta),
            {
                "correlation_id": "e1",
                "workflow_id": "w1",
                "source_system": "src",
                "message_received_at": "2025-01-01T00:00:00",
            },
        )


class TestCorrelationIdForLogger(unittest.TestCase):
    def test_correlation_id_for_logger_cases(self) -> None:
        cases = [
            ({}, None),
            ({"correlation_id": "N/A"}, None),
            ({"correlation_id": "evt-1"}, "evt-1"),
        ]
        for meta, expected in cases:
            with self.subTest(meta=meta):
                self.assertEqual(correlation_id_for_logger(meta), expected)
