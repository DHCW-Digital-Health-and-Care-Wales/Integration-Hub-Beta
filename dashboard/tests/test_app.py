"""
Unit tests for the Flask routes.
Uses Flask's built-in test client — no Azure credentials required.
All Azure service calls are mocked.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest
from dotenv import load_dotenv
from flask.testing import FlaskClient

from dashboard import app as app_module

app = app_module.app


@pytest.fixture()
def client() -> Generator[FlaskClient, None, None]:
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def _stub_retry_delay_metrics() -> Generator[None, None, None]:
    """Keep route tests offline by stubbing retry-delay metric queries."""
    with patch("dashboard.app.get_retry_delay_metrics_by_flow", return_value=[]):
        yield


EMPTY_QUEUES: list = []
EMPTY_EXCEPTIONS: list = []
EMPTY_MESSAGES: list = []
EMPTY_CONTAINER_METRICS: dict = {}


def _mock_patches() -> list:
    return [
        patch("dashboard.app.get_queues", return_value=EMPTY_QUEUES),
        patch("dashboard.app.get_exceptions", return_value=EMPTY_EXCEPTIONS),
        patch("dashboard.app.get_container_apps_metrics", return_value=EMPTY_CONTAINER_METRICS),
        patch("dashboard.services.azure_monitor.get_messages_today", return_value=EMPTY_MESSAGES),
    ]


class TestPageRoutes:
    def test_index_returns_200(self, client: FlaskClient) -> None:
        with (
            patch("dashboard.app.get_queues", return_value=EMPTY_QUEUES),
            patch("dashboard.app.get_exceptions", return_value=EMPTY_EXCEPTIONS),
            patch("dashboard.app.get_container_apps_metrics", return_value=EMPTY_CONTAINER_METRICS),
        ):
            response = client.get("/")
        assert response.status_code == 200

    def test_flows_returns_200(self, client: FlaskClient) -> None:
        with (
            patch("dashboard.app.get_queues", return_value=EMPTY_QUEUES),
            patch("dashboard.app.get_exceptions", return_value=EMPTY_EXCEPTIONS),
            patch("dashboard.app.get_container_apps_metrics", return_value=EMPTY_CONTAINER_METRICS),
        ):
            response = client.get("/flows")
        assert response.status_code == 200

    def test_exceptions_returns_200(self, client: FlaskClient) -> None:
        with (
            patch("dashboard.services.azure_monitor.get_exceptions", return_value=EMPTY_EXCEPTIONS),
            patch("dashboard.app.get_exceptions", return_value=EMPTY_EXCEPTIONS),
        ):
            response = client.get("/exceptions")
        assert response.status_code == 200

    def test_exceptions_empty_state_uses_config_flag(self, client: FlaskClient) -> None:
        with (
            patch("dashboard.services.azure_monitor.get_exceptions", return_value=EMPTY_EXCEPTIONS),
            patch("dashboard.app.get_exceptions", return_value=EMPTY_EXCEPTIONS),
            patch.object(app_module.config, "AZURE_LOG_ANALYTICS_WORKSPACE_ID", "workspace-id"),
        ):
            response = client.get("/exceptions")

        assert response.status_code == 200
        assert b"No exceptions were found in the last 24 hours" in response.data
        assert b"Azure Log Analytics credentials are not configured." not in response.data

    def test_service_bus_returns_200(self, client: FlaskClient) -> None:
        with patch("dashboard.app.get_queues", return_value=EMPTY_QUEUES):
            response = client.get("/service-bus")
        assert response.status_code == 200

    def test_messages_returns_200(self, client: FlaskClient) -> None:
        with patch("dashboard.app.get_messages_today", return_value=EMPTY_MESSAGES):
            response = client.get("/messages")
        assert response.status_code == 200

    def test_messages_empty_state_uses_config_flag(self, client: FlaskClient) -> None:
        with (
            patch("dashboard.app.get_messages_today", return_value=EMPTY_MESSAGES),
            patch.object(app_module.config, "AZURE_LOG_ANALYTICS_WORKSPACE_ID", "workspace-id"),
        ):
            response = client.get("/messages")

        assert response.status_code == 200
        assert b"No messages were processed today." in response.data
        assert b"credentials are not configured" not in response.data


class TestNavEnvLabel:
    """Tests that the environment chip renders correctly in the navbar."""

    def test_env_chip_shown_when_label_is_set(self, client: FlaskClient) -> None:
        with (
            patch("dashboard.app.config.ENVIRONMENT_LABEL", "TESTING"),
            patch("dashboard.app.config.ENVIRONMENT_COLOR", "#a855f7"),
            patch("dashboard.app.get_queues", return_value=EMPTY_QUEUES),
            patch("dashboard.app.get_exceptions", return_value=EMPTY_EXCEPTIONS),
            patch("dashboard.app.get_container_apps_metrics", return_value=EMPTY_CONTAINER_METRICS),
        ):
            response = client.get("/")
        assert b"nav-env-label" in response.data
        assert b"TESTING" in response.data

    def test_env_chip_hidden_when_label_is_empty(self, client: FlaskClient) -> None:
        with (
            patch("dashboard.app.config.ENVIRONMENT_LABEL", ""),
            patch("dashboard.app.config.ENVIRONMENT_COLOR", "#94a3b8"),
            patch("dashboard.app.get_queues", return_value=EMPTY_QUEUES),
            patch("dashboard.app.get_exceptions", return_value=EMPTY_EXCEPTIONS),
            patch("dashboard.app.get_container_apps_metrics", return_value=EMPTY_CONTAINER_METRICS),
        ):
            response = client.get("/")
        assert b"nav-env-label" not in response.data


class TestApiRoutes:
        with patch("dashboard.app._get_cached_status", side_effect=AssertionError("healthz should not query Azure")):
            response = client.get("/healthz")

        assert response.status_code == 200
        assert response.get_json() == {"status": "ok"}

    def test_api_status_returns_json(self, client: FlaskClient) -> None:
        with (
            patch("dashboard.app.get_queues", return_value=EMPTY_QUEUES),
            patch("dashboard.app.get_exceptions", return_value=EMPTY_EXCEPTIONS),
            patch("dashboard.app.get_container_apps_metrics", return_value=EMPTY_CONTAINER_METRICS),
        ):
            response = client.get("/api/status")
        assert response.status_code == 200
        data = response.get_json()
        assert "system_health" in data
        assert "kpis" in data

    def test_api_flows_returns_json(self, client: FlaskClient) -> None:
        with (
            patch("dashboard.app.get_queues", return_value=EMPTY_QUEUES),
            patch("dashboard.app.get_container_apps_metrics", return_value=EMPTY_CONTAINER_METRICS),
        ):
            response = client.get("/api/flows")
        assert response.status_code == 200
        data = response.get_json()
        assert "flows" in data

    def test_api_messages_returns_json(self, client: FlaskClient) -> None:
        with patch("dashboard.app.get_messages_today", return_value=EMPTY_MESSAGES):
            response = client.get("/api/messages")
        assert response.status_code == 200
        data = response.get_json()
        assert "messages" in data
        assert "count" in data

    def test_api_container_app_history_returns_json(self, client: FlaskClient) -> None:
        fake_history = {
            "name": "my-app",
            "timestamps": ["2024-01-01T00:00:00Z"],
            "cpu": [12.5],
            "memory_mb": [128.0],
        }
        with patch("dashboard.app.get_container_app_metric_history", return_value=fake_history) as mock_fn:
            response = client.get("/api/container-app/my-app/history")
        assert response.status_code == 200
        data = response.get_json()
        assert data == fake_history
        mock_fn.assert_called_once_with("my-app", hours=1)

    def test_api_container_app_history_accepts_valid_hours(self, client: FlaskClient) -> None:
        fake_history = {"name": "my-app", "timestamps": [], "cpu": [], "memory_mb": []}
        for hours_str, hours_int in [("1", 1), ("6", 6), ("24", 24), ("168", 168)]:
            with patch("dashboard.app.get_container_app_metric_history", return_value=fake_history) as mock_fn:
                response = client.get(f"/api/container-app/my-app/history?hours={hours_str}")
            assert response.status_code == 200
            mock_fn.assert_called_once_with("my-app", hours=hours_int)

    def test_api_container_app_history_defaults_to_1h_for_invalid_hours(self, client: FlaskClient) -> None:
        fake_history = {"name": "my-app", "timestamps": [], "cpu": [], "memory_mb": []}
        with patch("dashboard.app.get_container_app_metric_history", return_value=fake_history) as mock_fn:
            response = client.get("/api/container-app/my-app/history?hours=999")
        assert response.status_code == 200
        mock_fn.assert_called_once_with("my-app", hours=1)


class TestEnvLoading:
    def test_load_dotenv_sets_missing_values_only(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text(
            "AZURE_RESOURCE_GROUP=from-file\nAZURE_SERVICE_BUS_NAMESPACE=from-file-sb\n",
            encoding="utf-8",
        )

        monkeypatch.delenv("AZURE_RESOURCE_GROUP", raising=False)
        monkeypatch.setenv("AZURE_SERVICE_BUS_NAMESPACE", "pre-set")

        load_dotenv(env_file, override=False)

        assert os.environ["AZURE_RESOURCE_GROUP"] == "from-file"
        assert os.environ["AZURE_SERVICE_BUS_NAMESPACE"] == "pre-set"
