"""
Unit tests for the Flask routes.
Uses Flask's built-in test client — no Azure credentials required.
All Azure service calls are mocked.
"""

from __future__ import annotations

import io
import os
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest
from dotenv import load_dotenv
from flask.testing import FlaskClient

from dashboard import app as app_module
from dashboard.services import flow_sources

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
EMPTY_NAMESPACE_SNAPSHOT: dict = {
    "queues": [],
    "topics": [],
    "kpis": {
        "queue_active_messages": 0,
        "queue_dead_letter_messages": 0,
        "topic_active_messages": 0,
        "topic_dead_letter_messages": 0,
        "subscription_active_messages": 0,
        "subscription_dead_letter_messages": 0,
        "queue_count": 0,
        "topic_count": 0,
        "subscription_count": 0,
    },
}


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
            patch("dashboard.services.status_builder.get_namespace_snapshot", return_value=EMPTY_NAMESPACE_SNAPSHOT),
            patch("dashboard.services.status_builder.get_exceptions", return_value=EMPTY_EXCEPTIONS),
        ):
            response = client.get("/")
        assert response.status_code == 200

    def test_flows_returns_200(self, client: FlaskClient) -> None:
        with (
            patch("dashboard.services.status_builder.get_namespace_snapshot", return_value=EMPTY_NAMESPACE_SNAPSHOT),
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
        with patch("dashboard.routes.pages.cache.cached_nowait", return_value=EMPTY_NAMESPACE_SNAPSHOT):
            response = client.get("/service-bus")
        assert response.status_code == 200

    def test_service_bus_includes_topics_when_queues_are_empty(self, client: FlaskClient) -> None:
        snapshot = {
            **EMPTY_NAMESPACE_SNAPSHOT,
            "topics": [
                {
                    "name": "prefix-sbt-mpi-hl7-input",
                    "status": "Active",
                    "active_message_count": 2,
                    "dead_letter_message_count": 0,
                    "scheduled_message_count": 0,
                    "message_count": 2,
                    "subscriptions": [
                        {
                            "name": "prefix-sbs-outbound",
                            "entity_name": "prefix-sbt-mpi-hl7-input/prefix-sbs-outbound",
                            "status": "Active",
                            "active_message_count": 2,
                            "dead_letter_message_count": 0,
                            "message_count": 2,
                            "health": "healthy",
                            "consumer_apps": [
                                {
                                    "app_name": "sender-ca",
                                    "sender_type": "subscription_sender",
                                    "workflow_id": "mpi-to-topic",
                                }
                            ],
                        }
                    ],
                    "health": "healthy",
                }
            ],
            "kpis": {
                **EMPTY_NAMESPACE_SNAPSHOT["kpis"],
                "topic_count": 1,
                "subscription_count": 1,
                "topic_active_messages": 2,
                "subscription_active_messages": 2,
            },
        }
        with patch("dashboard.routes.pages.cache.cached_nowait", return_value=snapshot):
            response = client.get("/service-bus")

        assert response.status_code == 200
        assert b"prefix-sbt-mpi-hl7-input" in response.data
        assert b"prefix-sbs-outbound" in response.data

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

        def fake_microservice_ids(entity_type: str, entity_name: str) -> list[str]:
            return ["svc-a"] if entity_type == "queue" and entity_name == "queueA" else ["svc-b"]

        def fake_messages(microservice_ids: list[str] | None = None) -> list[dict]:
            count = 1 if microservice_ids == ["svc-a"] else 2
            return [
                {"timestamp": "2024-01-01T00:00:00", "event": "Processed", "app": "svc", "dimensions": {}}
                for _ in range(count)
            ]

        with (
            patch("dashboard.routes.pages.entity_to_microservice_ids", side_effect=fake_microservice_ids),
            patch("dashboard.routes.pages.get_messages_today", side_effect=fake_messages),
        ):
            response_a = client.get("/messages?queue=queueA")
            response_b = client.get("/messages?queue=queueB")

        assert response_a.status_code == 200
        assert response_b.status_code == 200
        assert b'<div class="kpi-number">1</div>' in response_a.data
        assert b'<div class="kpi-number">2</div>' in response_b.data

    def test_messages_accepts_subscription_filter(self, client: FlaskClient) -> None:
        with (
            patch("dashboard.routes.pages.entity_to_microservice_ids", return_value=["sub-sender"]),
            patch("dashboard.routes.pages.entity_to_workflow_id", return_value="mpi-to-topic"),
            patch("dashboard.routes.pages.get_flows", return_value={"mpi-to-topic": {"label": "MPI Outbound"}}),
            patch(
                "dashboard.routes.pages.get_messages_today",
                return_value=[
                    {
                        "timestamp": "2024-01-01T00:00:00",
                        "event": "Processed",
                        "app": "sub-sender",
                        "dimensions": {},
                    }
                ],
            ),
            patch(
                "dashboard.routes.pages.cache.cached_nowait",
                side_effect=[
                    [
                        {
                            "timestamp": "2024-01-01T00:00:00",
                            "event": "Processed",
                            "app": "sub-sender",
                            "dimensions": {},
                        }
                    ],
                    EMPTY_NAMESPACE_SNAPSHOT,
                ],
            ),
        ):
            response = client.get("/messages?entity_type=subscription&entity_name=topic-a/sub-a")

        assert response.status_code == 200
        assert b"topic-a/sub-a" in response.data


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
            patch("dashboard.services.status_builder.get_namespace_snapshot", return_value=EMPTY_NAMESPACE_SNAPSHOT),
            patch("dashboard.services.status_builder.get_exceptions", return_value=EMPTY_EXCEPTIONS),
        ):
            response = client.get("/")
        assert b"nav-env-label" in response.data
        assert b"TESTING" in response.data

    def test_env_chip_hidden_when_label_is_empty(self, client: FlaskClient) -> None:
        with (
            patch("dashboard.app.config.ENVIRONMENT_LABEL", ""),
            patch("dashboard.app.config.ENVIRONMENT_COLOR", "#94a3b8"),
            patch("dashboard.services.status_builder.get_namespace_snapshot", return_value=EMPTY_NAMESPACE_SNAPSHOT),
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
            patch("dashboard.services.status_builder.get_namespace_snapshot", return_value=EMPTY_NAMESPACE_SNAPSHOT),
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

    def test_api_messages_accepts_subscription_filter(self, client: FlaskClient) -> None:
        with (
            patch("dashboard.routes.api.entity_to_microservice_ids", return_value=["sub-sender"]),
            patch("dashboard.routes.api.get_messages_today", return_value=EMPTY_MESSAGES) as mock_messages,
        ):
            response = client.get("/api/messages?entity_type=subscription&entity_name=topic-a/sub-a")

        assert response.status_code == 200
        mock_messages.assert_called_once_with(microservice_ids=["sub-sender"])

    def test_api_servicebus_metrics_accepts_subscription_filters(self, client: FlaskClient) -> None:
        fake_metrics = {"incoming": [], "outgoing": [], "timespan": "1h"}
        with patch("dashboard.routes.api.get_message_metrics", return_value=fake_metrics) as mock_metrics:
            response = client.get("/api/servicebus-metrics?entity_type=subscription&entity_name=topic-a/sub-a")

        assert response.status_code == 200
        mock_metrics.assert_called_once_with(
            1,
            queue_name=None,
            entity_type="subscription",
            entity_name="topic-a/sub-a",
        )

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


class TestNetworkTestRoutes:
    def test_page_renders(self, client: FlaskClient) -> None:
        with (
            patch("dashboard.routes.pages.get_flows", return_value={}),
            patch("dashboard.routes.pages.flow_sources.list_sources", return_value=[]),
        ):
            response = client.get("/network-test")
        assert response.status_code == 200

    def test_source_endpoints_come_from_flow_sources_not_flows(self, client: FlaskClient) -> None:
        """Flow source servers must be entirely Cosmos-managed, independent of ARM-discovered flows."""
        fake_flows = {"phw-to-mpi": {"source": "PHW", "source_host": "phw.internal", "source_port": 2575}}
        fake_sources = [{"id": "1", "description": "Custom PHW", "url": "phw.example.nhs.uk", "port": 2575}]
        with (
            patch("dashboard.routes.pages.get_flows", return_value=fake_flows),
            patch("dashboard.routes.pages.flow_sources.list_sources", return_value=fake_sources),
        ):
            response = client.get("/network-test")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "Custom PHW" in body
        assert "phw.internal" not in body

    def test_api_list_returns_json(self, client: FlaskClient) -> None:
        endpoints = [{"host": "a.example.com", "port": 443, "latest": {"success": True}}]
        with (
            patch("dashboard.routes.api.network_test.list_tested_endpoints", return_value=endpoints),
            patch("dashboard.routes.api.get_flows", return_value={}),
            patch("dashboard.routes.api.flow_sources.list_sources", return_value=[]),
        ):
            response = client.get("/api/network-test/list")
        assert response.status_code == 200
        assert response.get_json() == {
            "endpoints": [{"host": "a.example.com", "port": 443, "latest": {"success": True}, "description": None}]
        }

    def test_api_list_matches_description_from_flow_source(self, client: FlaskClient) -> None:
        """Endpoints tested against a configured flow source server show its description."""
        endpoints = [{"host": "phw.example.nhs.uk", "port": 2575, "latest": {"success": True}}]
        sources = [{"id": "1", "description": "PHW Source", "url": "phw.example.nhs.uk", "port": 2575}]
        with (
            patch("dashboard.routes.api.network_test.list_tested_endpoints", return_value=endpoints),
            patch("dashboard.routes.api.get_flows", return_value={}),
            patch("dashboard.routes.api.flow_sources.list_sources", return_value=sources),
        ):
            response = client.get("/api/network-test/list")
        assert response.get_json()["endpoints"][0]["description"] == "PHW Source"

    def test_api_list_matches_description_from_flow_destination(self, client: FlaskClient) -> None:
        """Endpoints tested against a discovered flow destination show its destination name."""
        endpoints = [{"host": "mpi.example.nhs.uk", "port": 16005, "latest": {"success": True}}]
        flows = {
            "phw-to-mpi": {
                "destination": "MPI",
                "destination_host": "mpi.example.nhs.uk",
                "destination_port": 16005,
            }
        }
        with (
            patch("dashboard.routes.api.network_test.list_tested_endpoints", return_value=endpoints),
            patch("dashboard.routes.api.get_flows", return_value=flows),
            patch("dashboard.routes.api.flow_sources.list_sources", return_value=[]),
        ):
            response = client.get("/api/network-test/list")
        assert response.get_json()["endpoints"][0]["description"] == "MPI"

    def test_api_list_loads_flow_sources_once_for_all_endpoints(self, client: FlaskClient) -> None:
        """Configured flow sources should be loaded once per list request, not once per row."""
        endpoints = [
            {"host": "phw.example.nhs.uk", "port": 2575, "latest": {"success": True}},
            {"host": "other.example.nhs.uk", "port": 443, "latest": {"success": True}},
        ]
        sources = [{"id": "1", "description": "PHW Source", "url": "phw.example.nhs.uk", "port": 2575}]
        with (
            patch("dashboard.routes.api.network_test.list_tested_endpoints", return_value=endpoints),
            patch("dashboard.routes.api.get_flows", return_value={}),
            patch("dashboard.routes.api.flow_sources.list_sources", return_value=sources) as list_sources,
        ):
            response = client.get("/api/network-test/list")
        assert response.status_code == 200
        assert response.get_json()["endpoints"][0]["description"] == "PHW Source"
        assert response.get_json()["endpoints"][1]["description"] is None
        list_sources.assert_called_once_with()

    def test_api_list_ignores_incomplete_flow_source_records(self, client: FlaskClient) -> None:
        """Incomplete source records should be skipped rather than breaking the list API."""
        endpoints = [{"host": "phw.example.nhs.uk", "port": 2575, "latest": {"success": True}}]
        sources = [{"id": "1", "description": "PHW Source"}]
        with (
            patch("dashboard.routes.api.network_test.list_tested_endpoints", return_value=endpoints),
            patch("dashboard.routes.api.get_flows", return_value={}),
            patch("dashboard.routes.api.flow_sources.list_sources", return_value=sources),
        ):
            response = client.get("/api/network-test/list")
        assert response.status_code == 200
        assert response.get_json()["endpoints"][0]["description"] is None

    def test_api_list_does_not_mutate_tested_endpoint_records(self, client: FlaskClient) -> None:
        """The list API should not add presentation fields onto cached endpoint records."""
        endpoints = [{"host": "a.example.com", "port": 443, "latest": {"success": True}}]
        with (
            patch("dashboard.routes.api.network_test.list_tested_endpoints", return_value=endpoints),
            patch("dashboard.routes.api.get_flows", return_value={}),
            patch("dashboard.routes.api.flow_sources.list_sources", return_value=[]),
        ):
            response = client.get("/api/network-test/list")
        assert response.status_code == 200
        assert "description" not in endpoints[0]
        assert response.get_json()["endpoints"][0]["description"] is None

    def test_api_run_rejects_invalid_host(self, client: FlaskClient) -> None:
        response = client.post("/api/network-test/run", json={"host": "", "port": 443})
        assert response.status_code == 400
        assert "error" in response.get_json()

    def test_api_run_returns_result_without_warning_when_history_saved(self, client: FlaskClient) -> None:
        fake_result = {"host": "example.com", "port": 443, "success": True}
        with (
            patch("dashboard.routes.api.network_test.run_latency_test", return_value=fake_result),
            patch("dashboard.routes.api.network_test.save_history_sample", return_value=True),
        ):
            response = client.post("/api/network-test/run", json={"host": "example.com", "port": 443})
        assert response.status_code == 200
        assert "history_warning" not in response.get_json()

    def test_api_run_includes_warning_when_history_unreachable(self, client: FlaskClient) -> None:
        """The test result itself must still be returned even if Cosmos is unreachable."""
        fake_result = {"host": "example.com", "port": 443, "success": True}
        with (
            patch("dashboard.routes.api.network_test.run_latency_test", return_value=fake_result),
            patch("dashboard.routes.api.network_test.save_history_sample", return_value=False),
        ):
            response = client.post("/api/network-test/run", json={"host": "example.com", "port": 443})
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "history_warning" in data

    def test_api_history_get_returns_samples(self, client: FlaskClient) -> None:
        with patch("dashboard.routes.api.network_test.get_history", return_value=[{"timestamp": 1.0}]):
            response = client.get("/api/network-test/history?host=example.com&port=443")
        assert response.status_code == 200
        data = response.get_json()
        assert data["samples"] == [{"timestamp": 1.0}]

    def test_api_history_delete_removes_stored_data(self, client: FlaskClient) -> None:
        with patch("dashboard.routes.api.network_test.delete_history") as delete_history:
            response = client.delete("/api/network-test/history?host=example.com&port=443")
        assert response.status_code == 200
        assert response.get_json() == {"deleted": True, "host": "example.com", "port": 443}
        delete_history.assert_called_once_with("example.com", 443)

    def test_api_history_delete_rejects_invalid_port(self, client: FlaskClient) -> None:
        response = client.delete("/api/network-test/history?host=example.com&port=not-a-port")
        assert response.status_code == 400
        assert "error" in response.get_json()


class TestNetworkTestConfigRoutes:
    def test_config_page_renders(self, client: FlaskClient) -> None:
        with patch("dashboard.routes.pages.flow_sources.list_sources", return_value=[]):
            response = client.get("/network-test/config")
        assert response.status_code == 200

    def test_api_sources_get_returns_json(self, client: FlaskClient) -> None:
        sources = [{"id": "1", "description": "PHW", "url": "phw.example.nhs.uk", "port": 2575}]
        with patch("dashboard.routes.api.flow_sources.list_sources", return_value=sources):
            response = client.get("/api/network-test/sources")
        assert response.status_code == 200
        assert response.get_json() == {"sources": sources}

    def test_api_sources_post_adds_source(self, client: FlaskClient) -> None:
        added = {"id": "1", "description": "PHW", "url": "phw.example.nhs.uk", "port": 2575}
        with patch("dashboard.routes.api.flow_sources.add_source", return_value=added) as add_source:
            response = client.post(
                "/api/network-test/sources",
                json={"description": "PHW", "url": "phw.example.nhs.uk", "port": 2575},
            )
        assert response.status_code == 201
        assert response.get_json() == added
        add_source.assert_called_once_with("PHW", "phw.example.nhs.uk", 2575)

    def test_api_sources_post_rejects_invalid_body(self, client: FlaskClient) -> None:
        with patch("dashboard.routes.api.flow_sources.add_source", side_effect=flow_sources.InvalidSourceError("bad")):
            response = client.post("/api/network-test/sources", json={"description": "", "url": "", "port": ""})
        assert response.status_code == 400
        assert response.get_json() == {"error": "bad"}

    def test_api_sources_post_returns_persistence_error(self, client: FlaskClient) -> None:
        with patch(
            "dashboard.routes.api.flow_sources.add_source",
            side_effect=flow_sources.SourcePersistenceError("Source persistence is currently unavailable."),
        ):
            response = client.post(
                "/api/network-test/sources",
                json={"description": "PHW", "url": "phw.example.nhs.uk", "port": 2575},
            )
        assert response.status_code == 503
        assert response.get_json() == {"error": "Source persistence is currently unavailable."}

    def test_api_source_put_updates_source(self, client: FlaskClient) -> None:
        updated = {"id": "1", "description": "PHW", "url": "phw.example.nhs.uk", "port": 2575}
        with patch("dashboard.routes.api.flow_sources.update_source", return_value=updated) as update_source:
            response = client.put(
                "/api/network-test/sources/1",
                json={"description": "PHW", "url": "phw.example.nhs.uk", "port": 2575},
            )
        assert response.status_code == 200
        assert response.get_json() == updated
        update_source.assert_called_once_with("1", "PHW", "phw.example.nhs.uk", 2575)

    def test_api_source_delete_removes_source(self, client: FlaskClient) -> None:
        with patch("dashboard.routes.api.flow_sources.delete_source") as delete_source:
            response = client.delete("/api/network-test/sources/1")
        assert response.status_code == 200
        assert response.get_json() == {"deleted": True, "id": "1"}
        delete_source.assert_called_once_with("1")

    def test_api_source_delete_returns_persistence_error(self, client: FlaskClient) -> None:
        with patch(
            "dashboard.routes.api.flow_sources.delete_source",
            side_effect=flow_sources.SourcePersistenceError("Source persistence is currently unavailable."),
        ):
            response = client.delete("/api/network-test/sources/1")
        assert response.status_code == 503
        assert response.get_json() == {"error": "Source persistence is currently unavailable."}

    def test_api_sources_import_requires_file(self, client: FlaskClient) -> None:
        response = client.post("/api/network-test/sources/import", data={}, content_type="multipart/form-data")
        assert response.status_code == 400
        assert "error" in response.get_json()

    def test_api_sources_import_returns_summary(self, client: FlaskClient) -> None:
        csv_bytes = b"description,url,port\nPHW,phw.example.nhs.uk,2575\n"
        with patch(
            "dashboard.routes.api.flow_sources.import_sources",
            return_value={"imported": 1, "errors": [], "persistence_failed": False},
        ):
            response = client.post(
                "/api/network-test/sources/import",
                data={"file": (io.BytesIO(csv_bytes), "sources.csv")},
                content_type="multipart/form-data",
            )
        assert response.status_code == 200
        assert response.get_json() == {"imported": 1, "errors": [], "persistence_failed": False}

    def test_api_sources_import_returns_503_for_persistence_error(self, client: FlaskClient) -> None:
        csv_bytes = b"description,url,port\nPHW,phw.example.nhs.uk,2575\n"
        with patch(
            "dashboard.routes.api.flow_sources.import_sources",
            return_value={
                "imported": 0,
                "errors": ["Source persistence is currently unavailable."],
                "persistence_failed": True,
            },
        ):
            response = client.post(
                "/api/network-test/sources/import",
                data={"file": (io.BytesIO(csv_bytes), "sources.csv")},
                content_type="multipart/form-data",
            )
        assert response.status_code == 503
        assert response.get_json() == {
            "imported": 0,
            "errors": ["Source persistence is currently unavailable."],
            "persistence_failed": True,
        }


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
