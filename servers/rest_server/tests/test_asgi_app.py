import unittest
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from rest_server.asgi_app import build_fastapi_app


def _build_client(max_request_size_bytes: int = 1024) -> tuple[TestClient, MagicMock]:
    processor = MagicMock()
    processor.content_type = "application/xml; charset=utf-8"
    processor.content_adapter.build_error_response.side_effect = (
        lambda code, message: f"<error><code>{code}</code><message>{message}</message></error>"
    )
    processor.process.return_value = (200, "<ack/>")

    app = build_fastapi_app(
        processor=processor,
        endpoint_path="/ingest",
        max_request_size_bytes=max_request_size_bytes,
        content_adapter_name="xml-raw",
        validator_type="none",
        output_format="raw",
    )
    return TestClient(app, raise_server_exceptions=False), processor


class TestIngestEndpoint(unittest.TestCase):
    def setUp(self) -> None:
        self.client, self.processor = _build_client()

    def test_post_to_configured_path_is_forwarded_to_processor(self) -> None:
        response = self.client.post("/ingest", content=b"<Document/>")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "<ack/>")
        self.processor.process.assert_called_once_with("<Document/>")

    def test_post_to_unknown_path_returns_404(self) -> None:
        response = self.client.post("/unknown", content=b"<Document/>")

        self.assertEqual(response.status_code, 404)
        self.processor.process.assert_not_called()

    def test_get_on_ingest_path_returns_405(self) -> None:
        response = self.client.get("/ingest")

        self.assertEqual(response.status_code, 405)
        self.processor.process.assert_not_called()

    def test_empty_body_returns_400(self) -> None:
        response = self.client.post("/ingest", content=b"")

        self.assertEqual(response.status_code, 400)
        self.assertIn("Request body is empty", response.text)
        self.processor.process.assert_not_called()

    def test_non_utf8_body_returns_400(self) -> None:
        response = self.client.post("/ingest", content=b"\xff\xfe")

        self.assertEqual(response.status_code, 400)
        self.assertIn("UTF-8", response.text)
        self.processor.process.assert_not_called()

    def test_oversized_body_returns_413(self) -> None:
        client, processor = _build_client(max_request_size_bytes=10)

        response = client.post("/ingest", content=b"x" * 100)

        self.assertEqual(response.status_code, 413)
        self.assertIn("exceeds configured limit", response.text)
        processor.process.assert_not_called()


class TestHealthEndpoint(unittest.TestCase):
    def test_health_returns_ok(self) -> None:
        client, _ = _build_client()
        response = client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})


class TestOpenApiDocs(unittest.TestCase):
    def setUp(self) -> None:
        self.client, _ = _build_client()

    def test_openapi_schema_documents_configured_endpoint(self) -> None:
        response = self.client.get("/openapi.json")

        self.assertEqual(response.status_code, 200)
        schema = response.json()
        self.assertIn("/ingest", schema["paths"])
        self.assertIn("post", schema["paths"]["/ingest"])
        request_body_content = schema["paths"]["/ingest"]["post"]["requestBody"]["content"]
        self.assertIn("application/xml", request_body_content)

    def test_swagger_ui_is_reachable(self) -> None:
        response = self.client.get("/docs")

        self.assertEqual(response.status_code, 200)
        self.assertIn("swagger", response.text.lower())


if __name__ == "__main__":
    unittest.main()
