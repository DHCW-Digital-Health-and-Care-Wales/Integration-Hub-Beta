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
    """Keep route tests offline by stubbing retry-delay metric queries.

    ``get_retry_delay_metrics_by_flow`` is called from
    ``dashboard.services.status_builder.build_status`` (extracted from
    ``dashboard.app``), so it must be patched at its new home.
    """
    with patch("dashboard.services.status_builder.get_retry_delay_metrics_by_flow", return_value=[]):
        yield


EMPTY_QUEUES: list = []
EMPTY_EXCEPTIONS: list = []
EMPTY_MESSAGES: list = []
EMPTY_CONTAINER_METRICS: dict = {}


def _mock_patches() -> list:
    return [
        patch("dashboard.routes.api.get_queues", return_value=EMPTY_QUEUES),
        patch("dashboard.app.get_exceptions", return_value=EMPTY_EXCEPTIONS),
        patch("dashboard.routes.api.get_container_apps_metrics", return_value=EMPTY_CONTAINER_METRICS),
        patch("dashboard.services.azure_monitor.get_messages_today", return_value=EMPTY_MESSAGES),
    ]


class TestPageRoutes:
    def test_index_returns_200(self, client: FlaskClient) -> None:
        with (
            patch("dashboard.services.status_builder.get_queues", return_value=EMPTY_QUEUES),
            patch("dashboard.services.status_builder.get_exceptions", return_value=EMPTY_EXCEPTIONS),
        ):
            response = client.get("/")
        assert response.status_code == 200

    def test_flows_returns_200(self, client: FlaskClient) -> None:
        with (
            patch("dashboard.services.status_builder.get_queues", return_value=EMPTY_QUEUES),
            patch("dashboard.services.status_builder.get_exceptions", return_value=EMPTY_EXCEPTIONS),
            patch("dashboard.routes.pages.get_container_apps_metrics", return_value=EMPTY_CONTAINER_METRICS),
        ):
            response = client.get("/flows")
        assert response.status_code == 200

    def test_exceptions_returns_200(self, client: FlaskClient) -> None:
        with (
            patch("dashboard.services.azure_monitor.get_exceptions", return_value=EMPTY_EXCEPTIONS),
            patch("dashboard.routes.pages.get_exceptions", return_value=EMPTY_EXCEPTIONS),
        ):
            response = client.get("/exceptions")
        assert response.status_code == 200

    def test_exceptions_empty_state_uses_config_flag(self, client: FlaskClient) -> None:
        with (
            patch("dashboard.services.azure_monitor.get_exceptions", return_value=EMPTY_EXCEPTIONS),
            patch("dashboard.routes.pages.get_exceptions", return_value=EMPTY_EXCEPTIONS),
            patch.object(app_module.config, "AZURE_LOG_ANALYTICS_WORKSPACE_ID", "workspace-id"),
        ):
            response = client.get("/exceptions")

        assert response.status_code == 200
        assert b"No exceptions were found in the last 24 hours" in response.data
        assert b"Azure Log Analytics credentials are not configured." not in response.data

    def test_exceptions_non_numeric_hours_falls_back_to_default(self, client: FlaskClient) -> None:
        with (
            patch("dashboard.services.azure_monitor.get_exceptions", return_value=EMPTY_EXCEPTIONS),
            patch("dashboard.routes.pages.get_exceptions", return_value=EMPTY_EXCEPTIONS),
            patch.object(app_module.config, "AZURE_LOG_ANALYTICS_WORKSPACE_ID", "workspace-id"),
        ):
            response = client.get("/exceptions?hours=abc")
        assert response.status_code == 200
        assert b"No exceptions were found in the last 24 hours" in response.data

    def test_exceptions_rejects_hours_value_not_in_allowed_set(self, client: FlaskClient) -> None:
        with (
            patch("dashboard.services.azure_monitor.get_exceptions", return_value=EMPTY_EXCEPTIONS),
            patch("dashboard.routes.pages.get_exceptions", return_value=EMPTY_EXCEPTIONS),
            patch.object(app_module.config, "AZURE_LOG_ANALYTICS_WORKSPACE_ID", "workspace-id"),
        ):
            response = client.get("/exceptions?hours=999999999")
        assert response.status_code == 200
        assert b"No exceptions were found in the last 24 hours" in response.data

    def test_exceptions_accepts_valid_hours_from_dropdown(self, client: FlaskClient) -> None:
        with (
            patch("dashboard.services.azure_monitor.get_exceptions", return_value=EMPTY_EXCEPTIONS),
            patch("dashboard.routes.pages.get_exceptions", return_value=EMPTY_EXCEPTIONS),
            patch.object(app_module.config, "AZURE_LOG_ANALYTICS_WORKSPACE_ID", "workspace-id"),
        ):
            response = client.get("/exceptions?hours=72")
        assert response.status_code == 200
        assert b"No exceptions were found in the last 72 hours" in response.data

    def test_service_bus_returns_200(self, client: FlaskClient) -> None:
        with patch("dashboard.routes.pages.get_queues", return_value=EMPTY_QUEUES):
            response = client.get("/service-bus")
        assert response.status_code == 200

    def test_messages_returns_200(self, client: FlaskClient) -> None:
        with patch("dashboard.routes.pages.get_messages_today", return_value=EMPTY_MESSAGES):
            response = client.get("/messages")
        assert response.status_code == 200

    def test_messages_empty_state_uses_config_flag(self, client: FlaskClient) -> None:
        with (
            patch("dashboard.routes.pages.get_messages_today", return_value=EMPTY_MESSAGES),
            patch.object(app_module.config, "AZURE_LOG_ANALYTICS_WORKSPACE_ID", "workspace-id"),
        ):
            response = client.get("/messages")

        assert response.status_code == 200
        assert b"No messages were processed today." in response.data
        assert b"credentials are not configured" not in response.data

    def test_messages_cache_key_varies_by_queue_filter(self, client: FlaskClient) -> None:
        """Different queue filters must not share/overwrite the same cache entry."""

        def fake_microservice_ids(queue_name: str) -> list[str]:
            return ["svc-a"] if queue_name == "queueA" else ["svc-b"]

        def fake_messages(microservice_ids: list[str] | None = None) -> list[dict]:
            count = 1 if microservice_ids == ["svc-a"] else 2
            return [
                {"timestamp": "2024-01-01T00:00:00", "event": "Processed", "app": "svc", "dimensions": {}}
                for _ in range(count)
            ]

        with (
            patch("dashboard.routes.pages.queue_to_microservice_ids", side_effect=fake_microservice_ids),
            patch("dashboard.routes.pages.get_messages_today", side_effect=fake_messages),
        ):
            response_a = client.get("/messages?queue=queueA")
            response_b = client.get("/messages?queue=queueB")

        assert response_a.status_code == 200
        assert response_b.status_code == 200
        assert b'<div class="kpi-number">1</div>' in response_a.data
        assert b'<div class="kpi-number">2</div>' in response_b.data


class TestSetLanguage:
    """Tests for the /set-language redirect-target validation (CodeQL: open redirect)."""

    def test_redirects_to_relative_path_from_same_host_referrer(self, client: FlaskClient) -> None:
        response = client.post(
            "/set-language",
            data={"lang": "cy"},
            headers={"Referer": "http://localhost/flows"},
        )
        assert response.status_code == 302
        assert response.headers["Location"] == "/flows"

    def test_cross_host_referrer_is_stripped_to_relative_path(self, client: FlaskClient) -> None:
        response = client.post(
            "/set-language",
            data={"lang": "cy"},
            headers={"Referer": "http://evil.example.com/phish"},
        )
        assert response.status_code == 302
        assert response.headers["Location"] == "/phish"

    def test_backslash_bypass_is_normalised_and_stripped(self, client: FlaskClient) -> None:
        response = client.post(
            "/set-language",
            data={"lang": "cy"},
            headers={"Referer": "/\\evil.com"},
        )
        assert response.status_code == 302
        assert response.headers["Location"] == "/"

    def test_preserves_query_string_from_referrer(self, client: FlaskClient) -> None:
        response = client.post(
            "/set-language",
            data={"lang": "cy"},
            headers={"Referer": "http://localhost/messages?queue=pre-phw-transform"},
        )
        assert response.status_code == 302
        assert response.headers["Location"] == "/messages?queue=pre-phw-transform"

    def test_falls_back_to_index_when_no_referrer(self, client: FlaskClient) -> None:
        response = client.post("/set-language", data={"lang": "en"})
        assert response.status_code == 302
        assert response.headers["Location"] == "/"

    def test_invalid_lang_is_ignored_but_still_redirects(self, client: FlaskClient) -> None:
        with client.session_transaction() as sess:
            sess["lang"] = "en"
        response = client.post(
            "/set-language",
            data={"lang": "fr"},
            headers={"Referer": "http://localhost/flows"},
        )
        assert response.status_code == 302
        with client.session_transaction() as sess:
            assert sess["lang"] == "en"


class TestNavEnvLabel:
    """Tests that the environment chip renders correctly in the navbar."""

    def test_env_chip_shown_when_label_is_set(self, client: FlaskClient) -> None:
        with (
            patch("dashboard.app.config.ENVIRONMENT_LABEL", "TESTING"),
            patch("dashboard.app.config.ENVIRONMENT_COLOR", "#a855f7"),
            patch("dashboard.services.status_builder.get_queues", return_value=EMPTY_QUEUES),
            patch("dashboard.services.status_builder.get_exceptions", return_value=EMPTY_EXCEPTIONS),
        ):
            response = client.get("/")
        assert b"nav-env-label" in response.data
        assert b"TESTING" in response.data

    def test_env_chip_hidden_when_label_is_empty(self, client: FlaskClient) -> None:
        with (
            patch("dashboard.app.config.ENVIRONMENT_LABEL", ""),
            patch("dashboard.app.config.ENVIRONMENT_COLOR", "#94a3b8"),
            patch("dashboard.services.status_builder.get_queues", return_value=EMPTY_QUEUES),
            patch("dashboard.services.status_builder.get_exceptions", return_value=EMPTY_EXCEPTIONS),
        ):
            response = client.get("/")
        assert b"nav-env-label" not in response.data


class TestEmailAlertsConfigured:
    """Tests for _email_alerts_configured(), which gates the email-alert UI controls.

    Must mirror email_service.send_alert_email()'s guard exactly, so the UI never
    enables controls for a configuration that will silently fail to send.
    """

    def test_true_when_fully_configured_via_key_vault(self) -> None:
        with (
            patch.object(app_module.config, "ALERT_EMAIL_ENABLED", True),
            patch.object(app_module.config, "ACS_CONNECTION_STRING", ""),
            patch.object(app_module.config, "AZURE_KEY_VAULT_URL", "https://kv.vault.azure.net/"),
            patch.object(app_module.config, "ALERT_EMAIL_TO", "to@example.com"),
            patch.object(app_module.config, "ALERT_EMAIL_FROM", "from@example.com"),
        ):
            assert app_module._email_alerts_configured() is True

    def test_false_when_alert_email_disabled(self) -> None:
        with (
            patch.object(app_module.config, "ALERT_EMAIL_ENABLED", False),
            patch.object(app_module.config, "AZURE_KEY_VAULT_URL", "https://kv.vault.azure.net/"),
            patch.object(app_module.config, "ALERT_EMAIL_TO", "to@example.com"),
            patch.object(app_module.config, "ALERT_EMAIL_FROM", "from@example.com"),
        ):
            assert app_module._email_alerts_configured() is False

    def test_false_when_no_acs_source_configured(self) -> None:
        with (
            patch.object(app_module.config, "ALERT_EMAIL_ENABLED", True),
            patch.object(app_module.config, "ACS_CONNECTION_STRING", ""),
            patch.object(app_module.config, "AZURE_KEY_VAULT_URL", ""),
            patch.object(app_module.config, "ALERT_EMAIL_TO", "to@example.com"),
            patch.object(app_module.config, "ALERT_EMAIL_FROM", "from@example.com"),
        ):
            assert app_module._email_alerts_configured() is False

    def test_false_when_recipient_missing(self) -> None:
        with (
            patch.object(app_module.config, "ALERT_EMAIL_ENABLED", True),
            patch.object(app_module.config, "AZURE_KEY_VAULT_URL", "https://kv.vault.azure.net/"),
            patch.object(app_module.config, "ALERT_EMAIL_TO", ""),
            patch.object(app_module.config, "ALERT_EMAIL_FROM", "from@example.com"),
        ):
            assert app_module._email_alerts_configured() is False

    def test_false_when_sender_missing(self) -> None:
        """Regression test: previously ALERT_EMAIL_FROM was not checked, so the UI could
        enable email-alert controls even though send_alert_email() would always skip
        sending (it requires a sender address too)."""
        with (
            patch.object(app_module.config, "ALERT_EMAIL_ENABLED", True),
            patch.object(app_module.config, "AZURE_KEY_VAULT_URL", "https://kv.vault.azure.net/"),
            patch.object(app_module.config, "ALERT_EMAIL_TO", "to@example.com"),
            patch.object(app_module.config, "ALERT_EMAIL_FROM", ""),
        ):
            assert app_module._email_alerts_configured() is False


class TestApiRoutes:
    def test_healthz_does_not_query_azure(self, client: FlaskClient) -> None:
        with patch("dashboard.app._get_cached_status", side_effect=AssertionError("healthz should not query Azure")):
            response = client.get("/healthz")

        assert response.status_code == 200
        assert response.get_json() == {"status": "ok"}

    def test_api_status_returns_json(self, client: FlaskClient) -> None:
        with (
            patch("dashboard.services.status_builder.get_queues", return_value=EMPTY_QUEUES),
            patch("dashboard.services.status_builder.get_exceptions", return_value=EMPTY_EXCEPTIONS),
        ):
            response = client.get("/api/status")
        assert response.status_code == 200
        data = response.get_json()
        assert "system_health" in data
        assert "kpis" in data

    def test_api_flows_returns_json(self, client: FlaskClient) -> None:
        with (
            patch("dashboard.routes.api.get_queues", return_value=EMPTY_QUEUES),
            patch("dashboard.routes.api.get_container_apps_metrics", return_value=EMPTY_CONTAINER_METRICS),
        ):
            response = client.get("/api/flows")
        assert response.status_code == 200
        data = response.get_json()
        assert "flows" in data

    def test_api_messages_returns_json(self, client: FlaskClient) -> None:
        with patch("dashboard.routes.api.get_messages_today", return_value=EMPTY_MESSAGES):
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
        with patch("dashboard.routes.api.get_container_app_metric_history", return_value=fake_history) as mock_fn:
            response = client.get("/api/container-app/my-app/history")
        assert response.status_code == 200
        data = response.get_json()
        assert data == fake_history
        mock_fn.assert_called_once_with("my-app", hours=1)

    def test_api_container_app_history_accepts_valid_hours(self, client: FlaskClient) -> None:
        fake_history = {"name": "my-app", "timestamps": [], "cpu": [], "memory_mb": []}
        for hours_str, hours_int in [("1", 1), ("6", 6), ("24", 24), ("168", 168)]:
            with patch("dashboard.routes.api.get_container_app_metric_history", return_value=fake_history) as mock_fn:
                response = client.get(f"/api/container-app/my-app/history?hours={hours_str}")
            assert response.status_code == 200
            mock_fn.assert_called_once_with("my-app", hours=hours_int)

    def test_api_container_app_history_defaults_to_1h_for_invalid_hours(self, client: FlaskClient) -> None:
        fake_history = {"name": "my-app", "timestamps": [], "cpu": [], "memory_mb": []}
        with patch("dashboard.routes.api.get_container_app_metric_history", return_value=fake_history) as mock_fn:
            response = client.get("/api/container-app/my-app/history?hours=999")
        assert response.status_code == 200
        mock_fn.assert_called_once_with("my-app", hours=1)

    def test_api_hl7_throughput_returns_json(self, client: FlaskClient) -> None:
        fake_metrics = {"in": [{"time": "2024-01-01T00:00:00+00:00", "value": 5}], "out": []}
        with patch("dashboard.routes.api.get_hl7_throughput_metrics", return_value=fake_metrics) as mock_fn:
            response = client.get("/api/hl7-throughput")
        assert response.status_code == 200
        assert response.get_json() == fake_metrics
        mock_fn.assert_called_once_with(hours=24, health_board=None, service=None)

    def test_api_hl7_throughput_accepts_valid_hours(self, client: FlaskClient) -> None:
        fake_metrics: dict[str, list[dict]] = {"in": [], "out": []}
        for hours_str, hours_int in [("24", 24), ("72", 72), ("168", 168), ("336", 336), ("720", 720)]:
            with patch("dashboard.routes.api.get_hl7_throughput_metrics", return_value=fake_metrics) as mock_fn:
                response = client.get(f"/api/hl7-throughput?hours={hours_str}")
            assert response.status_code == 200
            mock_fn.assert_called_once_with(hours=hours_int, health_board=None, service=None)

    def test_api_hl7_throughput_defaults_to_24h_for_invalid_hours(self, client: FlaskClient) -> None:
        fake_metrics: dict[str, list[dict]] = {"in": [], "out": []}
        with patch("dashboard.routes.api.get_hl7_throughput_metrics", return_value=fake_metrics) as mock_fn:
            response = client.get("/api/hl7-throughput?hours=999")
        assert response.status_code == 200
        mock_fn.assert_called_once_with(hours=24, health_board=None, service=None)

    def test_api_hl7_throughput_passes_filters(self, client: FlaskClient) -> None:
        fake_metrics: dict[str, list[dict]] = {"in": [], "out": []}
        with patch("dashboard.routes.api.get_hl7_throughput_metrics", return_value=fake_metrics) as mock_fn:
            response = client.get("/api/hl7-throughput?health_board=PHW&service=phw-to-mpi")
        assert response.status_code == 200
        mock_fn.assert_called_once_with(hours=24, health_board="PHW", service="phw-to-mpi")


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
