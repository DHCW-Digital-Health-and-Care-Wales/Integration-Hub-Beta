import unittest

from ultra7.models import Endpoint, IterationSpec, Message, Project


class TestMessage(unittest.TestCase):
    def test_round_trip(self) -> None:
        message = Message(name="A01", format="hl7", content="MSH|^~\\&|...")
        restored = Message.from_dict(message.to_dict())
        self.assertEqual(restored.name, message.name)
        self.assertEqual(restored.format, message.format)
        self.assertEqual(restored.content, message.content)
        self.assertEqual(restored.id, message.id)

    def test_default_iteration_is_none(self) -> None:
        message = Message(name="A01", format="json", content="{}")
        self.assertIsNone(message.iteration)

    def test_default_enabled_is_true(self) -> None:
        message = Message(name="A01", format="json", content="{}")
        self.assertTrue(message.enabled)

    def test_round_trip_preserves_disabled_state(self) -> None:
        message = Message(name="A01", format="json", content="{}", enabled=False)
        restored = Message.from_dict(message.to_dict())
        self.assertFalse(restored.enabled)

    def test_round_trip_with_iteration(self) -> None:
        message = Message(
            name="A01",
            format="hl7",
            content="MSG000001",
            iteration=IterationSpec(start=3, end=9, mode="increment", step=2, pad_width=6),
        )
        restored = Message.from_dict(message.to_dict())
        self.assertIsNotNone(restored.iteration)
        assert restored.iteration is not None
        self.assertEqual(restored.iteration.start, 3)
        self.assertEqual(restored.iteration.end, 9)
        self.assertEqual(restored.iteration.mode, "increment")
        self.assertEqual(restored.iteration.step, 2)
        self.assertEqual(restored.iteration.pad_width, 6)


class TestIterationSpec(unittest.TestCase):
    def test_round_trip_list_mode(self) -> None:
        spec = IterationSpec(start=0, end=3, mode="list", values=["AAA", "BBB"])
        restored = IterationSpec.from_dict(spec.to_dict())
        self.assertEqual(restored.mode, "list")
        self.assertEqual(restored.values, ["AAA", "BBB"])

    def test_from_dict_defaults(self) -> None:
        spec = IterationSpec.from_dict({"start": 1, "end": 2})
        self.assertEqual(spec.mode, "increment")
        self.assertEqual(spec.step, 1)
        self.assertEqual(spec.pad_width, 0)
        self.assertEqual(spec.timestamp_format, "%Y%m%d%H%M%S")


class TestEndpoint(unittest.TestCase):
    def test_round_trip_mllp(self) -> None:
        endpoint = Endpoint(kind="mllp", host="127.0.0.1", port=2575)
        restored = Endpoint.from_dict(endpoint.to_dict())
        self.assertEqual(restored.kind, "mllp")
        self.assertEqual(restored.host, "127.0.0.1")
        self.assertEqual(restored.port, 2575)

    def test_round_trip_rest_with_headers(self) -> None:
        endpoint = Endpoint(kind="rest", url="https://example.test/ingest", headers={"X-Test": "1"})
        restored = Endpoint.from_dict(endpoint.to_dict())
        self.assertEqual(restored.url, "https://example.test/ingest")
        self.assertEqual(restored.headers, {"X-Test": "1"})

    def test_from_dict_defaults(self) -> None:
        endpoint = Endpoint.from_dict({})
        self.assertEqual(endpoint.kind, "mllp")
        self.assertEqual(endpoint.timeout_seconds, 5.0)


class TestProject(unittest.TestCase):
    def test_round_trip_with_messages(self) -> None:
        project = Project(
            name="Demo",
            endpoint=Endpoint(kind="rest", url="https://example.test"),
            messages=[Message(name="m1", format="json", content="{}")],
            repeat_count=3,
            delay_ms=250,
        )
        restored = Project.from_dict(project.to_dict())
        self.assertEqual(restored.name, "Demo")
        self.assertEqual(restored.repeat_count, 3)
        self.assertEqual(restored.delay_ms, 250)
        self.assertEqual(len(restored.messages), 1)
        self.assertEqual(restored.messages[0].name, "m1")


if __name__ == "__main__":
    unittest.main()
