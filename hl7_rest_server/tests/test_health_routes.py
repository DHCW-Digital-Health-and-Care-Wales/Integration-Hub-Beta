"""Tests for the health/liveness/readiness routes and swagger gating."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from hl7_rest_server.app import create_app
from tests.helpers import build_test_context, make_config


class HealthRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        context, _, _ = build_test_context()
        self.app = create_app(context)
        self.client = TestClient(self.app)

    def test_ping_returns_ok(self) -> None:
        response = self.client.get("/hl7MessageReceiver/ping")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("clientIp", body)
        self.assertIn("version", body)

    def test_status_reports_ok_without_timeout(self) -> None:
        response = self.client.get("/hl7MessageReceiver/status")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["timeout"])
        self.assertEqual(body["status"], 200)


class SwaggerGatingTests(unittest.TestCase):
    def test_docs_available_in_dev(self) -> None:
        context, _, _ = build_test_context(config=make_config(environment="DEV"))
        client = TestClient(create_app(context))
        self.assertEqual(client.get("/openapi.json").status_code, 200)
        self.assertEqual(client.get("/docs").status_code, 200)

    def test_docs_absent_in_production(self) -> None:
        context, _, _ = build_test_context(config=make_config(environment="PRD"))
        client = TestClient(create_app(context))
        self.assertEqual(client.get("/openapi.json").status_code, 404)
        self.assertEqual(client.get("/docs").status_code, 404)


if __name__ == "__main__":
    unittest.main()
