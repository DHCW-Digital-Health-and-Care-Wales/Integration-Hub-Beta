import unittest

from buswatch.servicebus_reader import (
    ServiceBusReader,
    _extract_queue_names,
    _extract_session_queue_names,
    _is_session_required_error,
    _serialize_application_properties,
)


class _FakeMessage:
    def __init__(self, body_chunks: list[bytes | memoryview] | Exception) -> None:
        self._body_chunks = body_chunks

    @property
    def body(self) -> list[bytes | memoryview]:
        if isinstance(self._body_chunks, Exception):
            raise self._body_chunks
        return self._body_chunks


class TestEmulatorConfigParsing(unittest.TestCase):
    def test_extract_queue_names_deduplicates_and_preserves_order(self) -> None:
        payload: dict[str, object] = {
            "UserConfig": {
                "Namespaces": [
                    {
                        "Queues": [
                            {"Name": "queue-a"},
                            {"Name": "queue-b"},
                            {"Name": "queue-a"},
                        ]
                    }
                ]
            }
        }

        queue_names = _extract_queue_names(payload)

        self.assertEqual(queue_names, ["queue-a", "queue-b"])

    def test_extract_session_queue_names_only_returns_session_enabled_queues(self) -> None:
        payload: dict[str, object] = {
            "UserConfig": {
                "Namespaces": [
                    {
                        "Queues": [
                            {"Name": "queue-a", "Properties": {"RequiresSession": True}},
                            {"Name": "queue-b", "Properties": {"RequiresSession": False}},
                            {"Name": "queue-c", "Properties": {}},
                        ]
                    }
                ]
            }
        }

        queue_names = _extract_session_queue_names(payload)

        self.assertEqual(queue_names, ["queue-a"])


class TestMessageFormatting(unittest.TestCase):
    def setUp(self) -> None:
        self.reader = object.__new__(ServiceBusReader)

    def test_serialize_application_properties_converts_binary_and_nested_values(self) -> None:
        properties = {
            b"binary-key": b"binary-value",
            "nested": {"a": 1},
            "count": 3,
        }

        serialized = _serialize_application_properties(properties)

        self.assertEqual(
            serialized,
            {
                "binary-key": "binary-value",
                "nested": '{"a": 1}',
                "count": "3",
            },
        )

    def test_decode_body_returns_utf8_text(self) -> None:
        message = _FakeMessage([b"MSH|^~\\&", memoryview(b"|ADT")])

        body = self.reader._decode_body(message)

        self.assertEqual(body, "MSH|^~\\&|ADT")

    def test_decode_body_returns_base64_for_binary_payloads(self) -> None:
        message = _FakeMessage([b"\xff\xfe"])

        body = self.reader._decode_body(message)

        self.assertEqual(body, "<binary body base64=//4=>")

    def test_decode_body_handles_unreadable_messages(self) -> None:
        message = _FakeMessage(RuntimeError("boom"))

        body = self.reader._decode_body(message)

        self.assertEqual(body, "<unable to decode body>")


class TestSessionErrorDetection(unittest.TestCase):
    def test_is_session_required_error_detects_next_available_session_hint(self) -> None:
        exc = RuntimeError(
            "If trying to receive from NEXT_AVAILABLE_SESSION, use max_wait_time on the ServiceBusReceiver to control the timeout."
        )

        self.assertTrue(_is_session_required_error(exc))


if __name__ == "__main__":
    unittest.main()
