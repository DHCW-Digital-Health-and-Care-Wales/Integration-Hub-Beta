"""
Unit tests for the Flask routes.
Uses Flask's built-in test client — no Azure credentials required.
All Azure service calls are mocked.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from dashboard.app import app


@pytest.fixture()
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


EMPTY_QUEUES: list = []
EMPTY_EXCEPTIONS: list = []
EMPTY_MESSAGES: list = []
EMPTY_CONTAINER_METRICS: dict = {}


def _mock_patches():
    return [
        patch("dashboard.app.get_queues", return_value=EMPTY_QUEUES),
        patch("dashboard.app.get_exceptions", return_value=EMPTY_EXCEPTIONS),
        patch("dashboard.app.get_container_apps_metrics", return_value=EMPTY_CONTAINER_METRICS),
        patch("dashboard.services.azure_monitor.get_messages_today", return_value=EMPTY_MESSAGES),
    ]


class TestPageRoutes:
    def test_index_returns_200(self, client: object) -> None:
        with patch("dashboard.app.get_queues", return_value=EMPTY_QUEUES), \
             patch("dashboard.app.get_exceptions", return_value=EMPTY_EXCEPTIONS), \
             patch("dashboard.app.get_container_apps_metrics", return_value=EMPTY_CONTAINER_METRICS):
            response = client.get("/")
        assert response.status_code == 200

    def test_flows_returns_200(self, client: object) -> None:
        with patch("dashboard.app.get_queues", return_value=EMPTY_QUEUES), \
             patch("dashboard.app.get_exceptions", return_value=EMPTY_EXCEPTIONS), \
             patch("dashboard.app.get_container_apps_metrics", return_value=EMPTY_CONTAINER_METRICS):
            response = client.get("/flows")
        assert response.status_code == 200

    def test_exceptions_returns_200(self, client: object) -> None:
        with patch("dashboard.services.azure_monitor.get_exceptions", return_value=EMPTY_EXCEPTIONS), \
             patch("dashboard.app.get_exceptions", return_value=EMPTY_EXCEPTIONS):
            response = client.get("/exceptions")
        assert response.status_code == 200

    def test_service_bus_returns_200(self, client: object) -> None:
        with patch("dashboard.app.get_queues", return_value=EMPTY_QUEUES):
            response = client.get("/service-bus")
        assert response.status_code == 200

    def test_messages_returns_200(self, client: object) -> None:
        with patch("dashboard.app.get_messages_today", return_value=EMPTY_MESSAGES):
            response = client.get("/messages")
        assert response.status_code == 200


class TestApiRoutes:
    def test_api_status_returns_json(self, client: object) -> None:
        with patch("dashboard.app.get_queues", return_value=EMPTY_QUEUES), \
             patch("dashboard.app.get_exceptions", return_value=EMPTY_EXCEPTIONS), \
             patch("dashboard.app.get_container_apps_metrics", return_value=EMPTY_CONTAINER_METRICS):
            response = client.get("/api/status")
        assert response.status_code == 200
        data = response.get_json()
        assert "system_health" in data
        assert "kpis" in data

    def test_api_flows_returns_json(self, client: object) -> None:
        with patch("dashboard.app.get_queues", return_value=EMPTY_QUEUES), \
             patch("dashboard.app.get_container_apps_metrics", return_value=EMPTY_CONTAINER_METRICS):
            response = client.get("/api/flows")
        assert response.status_code == 200
        data = response.get_json()
        assert "flows" in data

    def test_api_messages_returns_json(self, client: object) -> None:
        with patch("dashboard.app.get_messages_today", return_value=EMPTY_MESSAGES):
            response = client.get("/api/messages")
        assert response.status_code == 200
        data = response.get_json()
        assert "messages" in data
        assert "count" in data
