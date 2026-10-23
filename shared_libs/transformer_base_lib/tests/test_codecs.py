import unittest
from typing import Any

from transformer_base_lib.codecs import FhirJsonCodec, Hl7Er7Codec


class TestHl7Er7Codec(unittest.TestCase):
    def test_parse_and_serialise_round_trip(self) -> None:
        codec = Hl7Er7Codec()
        test_message_body = (
            "MSH|^~\\&|252|252|100|100|2025-05-05 23:23:32||ADT^A31^ADT_A05|202505052323364444|P|2.5\r"
        )

        parsed = codec.parse(test_message_body)
        serialised = codec.serialise(parsed)

        self.assertEqual(serialised.rstrip("\r"), test_message_body.rstrip("\r"))


class TestFhirJsonCodec(unittest.TestCase):
    def test_parse_delegates_to_injected_parse_fn(self) -> None:
        parse_fn_calls = []

        def fake_parse_fn(message_body: str) -> dict:
            parse_fn_calls.append(message_body)
            return {"body": message_body}

        codec: FhirJsonCodec[dict, Any] = FhirJsonCodec(parse_fn=fake_parse_fn)

        result = codec.parse("<xml/>")

        self.assertEqual(result, {"body": "<xml/>"})
        self.assertEqual(parse_fn_calls, ["<xml/>"])

    def test_serialise_calls_model_dump_json(self) -> None:
        class FakeBundle:
            def model_dump_json(self) -> str:
                return '{"resourceType": "Bundle"}'

        codec: FhirJsonCodec[str, FakeBundle] = FhirJsonCodec(parse_fn=lambda body: body)

        result = codec.serialise(FakeBundle())

        self.assertEqual(result, '{"resourceType": "Bundle"}')


if __name__ == "__main__":
    unittest.main()
