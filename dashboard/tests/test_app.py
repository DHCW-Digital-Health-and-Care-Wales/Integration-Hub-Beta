"""
Unit tests for the Flask routes.
Uses Flask's built-in test client — no Azure credentials required.
All Azure service calls are mocked.
"""

from __future__ import annotations

import io
import os
import re
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from dotenv import load_dotenv
from flask.testing import FlaskClient
from werkzeug.test import TestResponse

from dashboard import app as app_module
from dashboard.routes import alarms as alarms_routes
from dashboard.services import contacts_store, flow_sources
from dashboard.services.flows import build_flow_options

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

    def test_flows_renders_topic_to_topic_pipeline(self, client: FlaskClient) -> None:
        phw_flows = {
            "phw-to-mpi": {
                "label": "PHW → MPI",
                "source": "PHW",
                "source_port": 2575,
                "pre_queue": None,
                "transformer": "PHW Transformer",
                "post_queue": None,
                "topic": "sbt-phw-hl7-input",
                "post_topic": "sbt-phw-hl7-output",
                "subscriptions": [
                    {"name": "sbs-phw-tfmr", "topic": "sbt-phw-hl7-input"},
                    {"name": "sbs-phw-mpi-sndr", "topic": "sbt-phw-hl7-output"},
                ],
                "destination": "MPI",
                "colour": "#3b82f6",
                "icon": "bi-heart-pulse",
            }
        }
        snapshot = {
            **EMPTY_NAMESPACE_SNAPSHOT,
            "topics": [
                {
                    "name": "sbt-phw-hl7-input",
                    "active_message_count": 0,
                    "dead_letter_message_count": 0,
                    "subscriptions": [
                        {
                            "name": "sbs-phw-tfmr",
                            "topic": "sbt-phw-hl7-input",
                            "status": "Active",
                            "active_message_count": 2,
                            "dead_letter_message_count": 0,
                            "message_count": 2,
                        }
                    ],
                },
                {
                    "name": "sbt-phw-hl7-output",
                    "active_message_count": 0,
                    "dead_letter_message_count": 0,
                    "subscriptions": [
                        {
                            "name": "sbs-phw-mpi-sndr",
                            "topic": "sbt-phw-hl7-output",
                            "status": "Active",
                            "active_message_count": 4,
                            "dead_letter_message_count": 0,
                            "message_count": 4,
                        }
                    ],
                },
            ],
        }
        with (
            patch("dashboard.services.status_builder.get_namespace_snapshot", return_value=snapshot),
            patch("dashboard.services.status_builder.get_active_flows", return_value=phw_flows),
            patch("dashboard.services.status_builder.get_exceptions", return_value=EMPTY_EXCEPTIONS),
            patch("dashboard.routes.pages.get_container_apps_metrics", return_value=EMPTY_CONTAINER_METRICS),
        ):
            from dashboard.services import cache as cache_mod  # noqa: PLC0415

            with cache_mod.cache_lock:
                cache_mod.cache_data.clear()
            response = client.get("/flows")

        assert response.status_code == 200
        assert b"sbt-phw-hl7-input" in response.data
        assert b"sbs-phw-tfmr" in response.data
        assert b"PHW Transformer" in response.data
        assert b"sbt-phw-hl7-output" in response.data
        assert b"sbs-phw-mpi-sndr" in response.data
        assert b"OUTPUT TOPIC" in response.data
        assert b'data-sub-node="sbt-phw-hl7-input/sbs-phw-tfmr"' in response.data
        assert b'data-sub-card="sbt-phw-hl7-input/sbs-phw-tfmr"' in response.data
        assert b'data-sub-node="sbt-phw-hl7-output/sbs-phw-mpi-sndr"' in response.data
        assert b'data-sub-card="sbt-phw-hl7-output/sbs-phw-mpi-sndr"' in response.data
        assert b'data-sub-arrow="sbt-phw-hl7-output/sbs-phw-mpi-sndr"' in response.data

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
            patch("dashboard.routes.pages.entity_to_flow_ids", return_value=["mpi-to-topic"]),
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
            patch("dashboard.routes.api.get_cached_status", return_value={"flows": []}),
            patch("dashboard.routes.api.get_container_apps_metrics", return_value=EMPTY_CONTAINER_METRICS),
        ):
            response = client.get("/api/flows")
        assert response.status_code == 200
        data = response.get_json()
        assert "flows" in data
        assert "container_metrics" in data

    def test_api_refresh_rebuilds_flow_definitions(self, client: FlaskClient) -> None:
        with (
            patch("dashboard.routes.api.discover_flows") as mock_discover,
            patch("dashboard.routes.api.get_active_flows", return_value={"wds-to-phw": {}}) as mock_active,
            patch("dashboard.routes.api.get_cached_status", return_value={}),
        ):
            response = client.get("/api/refresh")

        assert response.status_code == 200
        mock_discover.assert_called_once_with(force=True)
        mock_active.assert_called_once_with(force_refresh=True)
        assert response.get_json()["active_flows"] == ["wds-to-phw"]

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

    def test_api_hl7_throughput_serves_cached_response_on_repeat_request(self, client: FlaskClient) -> None:
        fake_metrics = {"incoming": [{"time": "2024-01-01T00:00:00+00:00", "value": 5}], "outgoing": []}
        with patch("dashboard.routes.api.get_hl7_throughput_metrics", return_value=fake_metrics) as mock_fn:
            r1 = client.get("/api/hl7-throughput?hours=24")
            r2 = client.get("/api/hl7-throughput?hours=24")
        assert r1.status_code == 200 and r2.status_code == 200
        assert r2.get_json() == fake_metrics
        mock_fn.assert_called_once()

    def test_api_servicebus_metrics_serves_cached_response_on_repeat_request(self, client: FlaskClient) -> None:
        fake_metrics = {"incoming": [], "outgoing": [], "timespan": "6h"}
        with patch("dashboard.routes.api.get_message_metrics", return_value=fake_metrics) as mock_fn:
            client.get("/api/servicebus-metrics?hours=6")
            client.get("/api/servicebus-metrics?hours=6")
        mock_fn.assert_called_once()

    def test_api_container_app_history_serves_cached_response_on_repeat_request(self, client: FlaskClient) -> None:
        fake_history = {"name": "my-app", "timestamps": [], "cpu": [], "memory_mb": []}
        with patch("dashboard.routes.api.get_container_app_metric_history", return_value=fake_history) as mock_fn:
            client.get("/api/container-app/my-app/history?hours=6")
            client.get("/api/container-app/my-app/history?hours=6")
        mock_fn.assert_called_once()

    def test_messages_page_does_not_fetch_unused_namespace_snapshot(self, client: FlaskClient) -> None:
        with (
            patch("dashboard.routes.pages.get_messages_today", return_value=EMPTY_MESSAGES),
            patch("dashboard.routes.pages.get_namespace_snapshot") as mock_sb,
        ):
            response = client.get("/messages")
        assert response.status_code == 200
        mock_sb.assert_not_called()

    def test_trace_page_caches_successful_traces_only(self, client: FlaskClient) -> None:
        ok_trace = {
            "spans": [
                {
                    "name": "op",
                    "duration": 1.0,
                    "success": True,
                    "target": "",
                    "app_name": "a",
                    "start_time": "",
                    "parent_id": "",
                }
            ],
            "exceptions": [],
            "logs": [],
            "duration_ms": 1.0,
            "start_time": "",
            "ok": True,
        }
        miss_trace = {"spans": [], "exceptions": [], "logs": [], "duration_ms": 0, "start_time": "", "ok": False}
        with patch("dashboard.routes.pages.get_trace", return_value=ok_trace) as mock_ok:
            assert client.get("/trace/op-hit").status_code == 200
            assert client.get("/trace/op-hit").status_code == 200
        mock_ok.assert_called_once_with("op-hit")

        with patch("dashboard.routes.pages.get_trace", return_value=miss_trace) as mock_miss:
            assert client.get("/trace/op-miss").status_code == 404
            assert client.get("/trace/op-miss").status_code == 404
        assert mock_miss.call_count == 2


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

    def test_api_list_ignores_non_mapping_flow_source_records(self, client: FlaskClient) -> None:
        """Non-dict source entries should be skipped rather than breaking the list API."""
        endpoints = [{"host": "phw.example.nhs.uk", "port": 2575, "latest": {"success": True}}]
        with (
            patch("dashboard.routes.api.network_test.list_tested_endpoints", return_value=endpoints),
            patch("dashboard.routes.api.get_flows", return_value={}),
            patch("dashboard.routes.api.flow_sources.list_sources", return_value=[None]),
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

    def test_api_list_ignores_incomplete_tested_endpoint_records(self, client: FlaskClient) -> None:
        """Incomplete tested endpoints should be skipped rather than breaking the list API."""
        endpoints = [
            {"latest": {"success": False}},
            {"host": "a.example.com", "port": 443, "latest": {"success": True}},
        ]
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


class TestAlarmsByFlowRoutes:
    FLOWS: dict[str, dict[str, Any]] = {
        "phw-to-mpi": {"label": "PHW → MPI"},
        "pims-to-mpi": {"label": "PIMS → MPI"},
    }

    def _get(
        self,
        client: FlaskClient,
        url: str,
        cfg1: list[dict] | None = None,
        cfg2: list[dict] | None = None,
        cfg3: list[dict] | None = None,
        statuses: tuple[list[dict] | None, list[dict] | None, list[dict] | None] = ([], [], []),
    ) -> tuple[TestResponse, int]:
        with (
            patch("dashboard.routes.alarms.get_flows", return_value=self.FLOWS),
            patch("dashboard.routes.alarms.get_config_page_data", return_value=cfg1 or []),
            patch("dashboard.routes.alarms.get_alarm2_config_page_data", return_value=cfg2 or []),
            patch("dashboard.routes.alarms.get_alarm3_config_page_data", return_value=cfg3 or []),
            patch("dashboard.routes.alarms.cache.multi_cached_nowait", return_value=statuses) as mock_cache,
        ):
            response = client.get(url)
        return response, mock_cache.call_count

    def test_overview_has_view_by_flow_button(self, client: FlaskClient) -> None:
        with patch("dashboard.routes.alarms.cache.multi_cached_nowait", return_value=([], [], [])):
            response = client.get("/alarms")
        assert response.status_code == 200
        assert b"View by Flow" in response.data
        assert b'href="/alarms/by-flow"' in response.data

    def test_no_flow_selected_shows_prompt_and_skips_status_fetch(self, client: FlaskClient) -> None:
        response, cache_calls = self._get(client, "/alarms/by-flow")
        assert response.status_code == 200
        assert b"Select a flow to view its alarms." in response.data
        assert b'data-flow-id="phw-to-mpi"' in response.data
        assert cache_calls == 0

    def test_unknown_flow_is_treated_as_unselected(self, client: FlaskClient) -> None:
        response, cache_calls = self._get(client, "/alarms/by-flow?flow=not-a-flow")
        assert response.status_code == 200
        assert b"Select a flow to view its alarms." in response.data
        assert cache_calls == 0

    def test_workflow_only_in_alarm_config_appears_in_dropdown(self, client: FlaskClient) -> None:
        cfg3 = [{"id": "wds-failures", "display_name": "WDS", "workflow_id": "wds-to-mpi", "alarm_enabled": True}]
        response, _ = self._get(client, "/alarms/by-flow", cfg3=cfg3)
        assert b'data-flow-id="wds-to-mpi"' in response.data

    def test_selected_flow_shows_only_its_alarm_rows(self, client: FlaskClient) -> None:
        a1 = [
            {"id": "phw-inactivity", "display_name": "PHW Inactivity", "workflow_id": "phw-to-mpi",
             "status": "critical", "alerting_gap_minutes": 30},
            {"id": "pims-inactivity", "display_name": "PIMS Inactivity", "workflow_id": "pims-to-mpi",
             "status": "healthy", "alerting_gap_minutes": 30},
        ]
        a3 = [
            {"id": "phw-failures", "display_name": "PHW Failures", "workflow_id": "phw-to-mpi",
             "status": "healthy", "failure_display": "0", "threshold": 5, "alerting_gap_minutes": 60},
        ]
        response, cache_calls = self._get(client, "/alarms/by-flow?flow=phw-to-mpi", statuses=(a1, [], a3))
        assert response.status_code == 200
        assert b"PHW Inactivity" in response.data
        assert b"PHW Failures" in response.data
        assert b"PIMS Inactivity" not in response.data
        # Alarm 2 has no rules for this flow, so its section shows the empty-state row.
        assert b"No rules are configured for this flow." in response.data
        assert cache_calls == 1
        # Search field and hidden flow id are pre-filled with the current selection.
        assert 'value="PHW → MPI (phw-to-mpi)"'.encode() in response.data
        assert b'id="flow-id-input" value="phw-to-mpi"' in response.data


class TestRowsForFlow:
    def test_filters_status_rows_by_workflow(self) -> None:
        status = [{"id": "a", "workflow_id": "x", "status": "healthy"}, {"id": "b", "workflow_id": "y"}]
        assert [r["id"] for r in alarms_routes._rows_for_flow(status, [], "x")] == ["a"]

    def test_adds_disabled_rules_from_config(self) -> None:
        cfg = [{"id": "c", "workflow_id": "x", "alarm_enabled": False}]
        rows = alarms_routes._rows_for_flow([], cfg, "x")
        assert rows == [{"id": "c", "workflow_id": "x", "alarm_enabled": False, "status": "disabled"}]

    def test_enabled_rule_missing_from_cold_cache_is_unknown(self) -> None:
        cfg = [{"id": "c", "workflow_id": "x", "alarm_enabled": True}]
        rows = alarms_routes._rows_for_flow(None, cfg, "x")
        assert rows[0]["status"] == "unknown"

    def test_config_row_does_not_duplicate_live_status_row(self) -> None:
        status = [{"id": "c", "workflow_id": "x", "status": "critical"}]
        cfg = [{"id": "c", "workflow_id": "x", "alarm_enabled": True}]
        rows = alarms_routes._rows_for_flow(status, cfg, "x")
        assert rows == status

    def test_empty_inputs_return_empty_list(self) -> None:
        assert alarms_routes._rows_for_flow(None, [], "x") == []


class TestFlowOptions:
    def test_merges_and_sorts_by_label(self) -> None:
        flows = {"pims-to-mpi": {"label": "PIMS → MPI"}, "phw-to-mpi": {"label": "PHW → MPI"}}
        cfg = [{"workflow_id": "abc-flow"}, {"workflow_id": "phw-to-mpi"}, {"workflow_id": ""}]
        options = build_flow_options(flows, cfg)
        assert options == [
            {"id": "abc-flow", "label": "abc-flow"},
            {"id": "phw-to-mpi", "label": "PHW → MPI"},
            {"id": "pims-to-mpi", "label": "PIMS → MPI"},
        ]


class TestContactsRoutes:
    def test_contacts_page_renders(self, client: FlaskClient) -> None:
        with patch("dashboard.routes.contacts.get_active_flows", return_value={}):
            response = client.get("/contacts")
        assert response.status_code == 200

    def test_api_contacts_get_returns_json(self, client: FlaskClient) -> None:
        contacts = [{"id": "1", "first_name": "Jane", "last_name": "Doe"}]
        with patch("dashboard.routes.contacts.contacts_store.list_contacts", return_value=(contacts, 1)):
            response = client.get("/api/contacts?q=jane&page=1&per_page=25")
        assert response.status_code == 200
        assert response.get_json() == {"contacts": contacts, "total": 1, "page": 1, "per_page": 25}

    def test_api_contacts_post_adds_contact(self, client: FlaskClient) -> None:
        added = {"id": "1", "first_name": "Jane", "last_name": "Doe"}
        with patch("dashboard.routes.contacts.contacts_store.add_contact", return_value=added) as add_contact:
            response = client.post(
                "/api/contacts",
                json={"first_name": "Jane", "last_name": "Doe", "email": "jane@example.nhs.uk"},
            )
        assert response.status_code == 201
        assert response.get_json() == added
        add_contact.assert_called_once()

    def test_api_contacts_post_rejects_invalid_body(self, client: FlaskClient) -> None:
        with patch(
            "dashboard.routes.contacts.contacts_store.add_contact",
            side_effect=contacts_store.InvalidContactError("bad"),
        ):
            response = client.post("/api/contacts", json={"first_name": ""})
        assert response.status_code == 400
        assert response.get_json() == {"error": "bad"}

    def test_api_contacts_post_returns_persistence_error(self, client: FlaskClient) -> None:
        with patch(
            "dashboard.routes.contacts.contacts_store.add_contact",
            side_effect=contacts_store.ContactPersistenceError("Contact persistence is currently unavailable."),
        ):
            response = client.post(
                "/api/contacts",
                json={"first_name": "Jane", "last_name": "Doe", "email": "jane@example.nhs.uk"},
            )
        assert response.status_code == 503
        assert response.get_json() == {"error": "Contact persistence is currently unavailable."}

    def test_api_contact_get_returns_404_for_unknown_id(self, client: FlaskClient) -> None:
        with patch("dashboard.routes.contacts.contacts_store.get_contact", return_value=None):
            response = client.get("/api/contacts/missing-id")
        assert response.status_code == 404

    def test_api_contact_put_updates_contact(self, client: FlaskClient) -> None:
        updated = {"id": "1", "first_name": "Jane", "last_name": "Smith"}
        with patch("dashboard.routes.contacts.contacts_store.update_contact", return_value=updated):
            response = client.put(
                "/api/contacts/1",
                json={"first_name": "Jane", "last_name": "Smith", "email": "jane@example.nhs.uk"},
            )
        assert response.status_code == 200
        assert response.get_json() == updated

    def test_api_contact_delete_soft_deletes(self, client: FlaskClient) -> None:
        with patch("dashboard.routes.contacts.contacts_store.delete_contact") as delete_contact:
            response = client.delete("/api/contacts/1")
        assert response.status_code == 200
        assert response.get_json() == {"deleted": True, "id": "1"}
        delete_contact.assert_called_once_with("1")

    def test_api_contacts_import_returns_summary(self, client: FlaskClient) -> None:
        csv_bytes = (
            b"first_name,last_name,email,phone_number,organisation_type,organisation_name,flow_ids,notes\n"
            b"Jane,Doe,jane@example.nhs.uk,,Team,Hub Team,,\n"
        )
        with patch(
            "dashboard.routes.contacts.contacts_store.import_contacts",
            return_value={"created": 1, "updated": 0, "errors": [], "persistence_failed": False},
        ):
            response = client.post(
                "/api/contacts/import",
                data={"file": (io.BytesIO(csv_bytes), "contacts.csv")},
                content_type="multipart/form-data",
            )
        assert response.status_code == 200
        assert response.get_json() == {"created": 1, "updated": 0, "errors": [], "persistence_failed": False}

    def test_api_contacts_import_returns_503_for_persistence_error(self, client: FlaskClient) -> None:
        csv_bytes = (
            b"first_name,last_name,email,phone_number,organisation_type,organisation_name,flow_ids,notes\n"
            b"Jane,Doe,jane@example.nhs.uk,,Team,Hub Team,,\n"
        )
        with patch(
            "dashboard.routes.contacts.contacts_store.import_contacts",
            return_value={
                "created": 0,
                "updated": 0,
                "errors": ["Contact persistence is currently unavailable."],
                "persistence_failed": True,
            },
        ):
            response = client.post(
                "/api/contacts/import",
                data={"file": (io.BytesIO(csv_bytes), "contacts.csv")},
                content_type="multipart/form-data",
            )
        assert response.status_code == 503

    def test_api_contacts_import_rejects_missing_file(self, client: FlaskClient) -> None:
        response = client.post("/api/contacts/import", data={}, content_type="multipart/form-data")
        assert response.status_code == 400


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


class TestUIQuickWins:
    """Regression checks for shared CSS classes, navbar active states, and live-refresh markup."""

    def test_flows_page_has_single_flow_no_results_id(self, client: FlaskClient) -> None:
        with (
            patch("dashboard.services.status_builder.get_namespace_snapshot", return_value=EMPTY_NAMESPACE_SNAPSHOT),
            patch("dashboard.services.status_builder.get_exceptions", return_value=EMPTY_EXCEPTIONS),
            patch("dashboard.routes.pages.get_container_apps_metrics", return_value=EMPTY_CONTAINER_METRICS),
        ):
            response = client.get("/flows")
        assert response.status_code == 200
        assert response.data.count(b'id="flow-no-results"') == 1

    def test_alarm_pauses_page_highlights_alarms_nav_link(self, client: FlaskClient) -> None:
        response = client.get("/alarms/pauses")
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert 'class="nav-link active"' in html
        assert 'href="/alarms"' in html

    def test_network_test_config_page_highlights_network_test_nav_link(self, client: FlaskClient) -> None:
        response = client.get("/network-test/config")
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert 'class="nav-link active"\n             href="/network-test"' in html

    def test_overview_flow_rows_carry_data_href(self, client: FlaskClient) -> None:
        with (
            patch("dashboard.services.status_builder.get_namespace_snapshot", return_value=EMPTY_NAMESPACE_SNAPSHOT),
            patch("dashboard.services.status_builder.get_exceptions", return_value=EMPTY_EXCEPTIONS),
        ):
            response = client.get("/")
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert 'class="flow-row"' in html
        assert 'data-href="/flows#flow-' in html

    def test_shared_css_defines_used_classes_and_variables(self) -> None:
        css_path = Path(app_module.__file__).resolve().parent / "static" / "css" / "style.css"
        css = css_path.read_text(encoding="utf-8")

        for selector in (
            ".btn-dash--primary",
            ".btn-dash-sm",
            ".cfg-label",
            ".cfg-hint",
            ".table-danger-row",
        ):
            assert selector in css, f"Expected {selector} to be defined in style.css"

        defined_vars = set(re.findall(r"(--[a-zA-Z0-9-]+)\s*:", css))
        used_vars = set(re.findall(r"var\((--[a-zA-Z0-9-]+)\)", css))
        assert used_vars - defined_vars == set()

    def test_dashboard_js_preserves_flow_health_badge_class_on_refresh(self) -> None:
        js_path = Path(app_module.__file__).resolve().parent / "static" / "js" / "dashboard.js"
        js = js_path.read_text(encoding="utf-8")
        badge_block = js.split('card.querySelector(".flow-health-badge")', 1)[1][:500]
        assert "badge.className =" not in badge_block
        assert 'badge.classList.remove("healthy", "warning", "critical", "unknown")' in badge_block
        assert 'badge.querySelector(".flow-status-dot")' in badge_block

    def test_theme_toggle_dispatches_event_and_charts_listen(self, client: FlaskClient) -> None:
        with (
            patch("dashboard.services.status_builder.get_namespace_snapshot", return_value=EMPTY_NAMESPACE_SNAPSHOT),
            patch("dashboard.services.status_builder.get_exceptions", return_value=EMPTY_EXCEPTIONS),
        ):
            response = client.get("/")
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "ih-theme-change" in html
        assert "background: #1B294A;" in html

        js_dir = Path(app_module.__file__).resolve().parent / "static" / "js"
        for filename in (
            "hl7-throughput-chart.js",
            "sb-chart.js",
            "network-test-chart.js",
            "app-history.js",
        ):
            content = (js_dir / filename).read_text(encoding="utf-8")
            assert "ih-theme-change" in content, f"Expected {filename} to redraw on theme change"

    def test_light_mode_table_and_exception_hover_styles(self) -> None:
        css_path = Path(app_module.__file__).resolve().parent / "static" / "css" / "style.css"
        css = css_path.read_text(encoding="utf-8")
        assert ".exception-item:hover { background: var(--bg-card-hover); }" in css
        assert "rgba(100,116,139,0.4)" not in css

    def test_noc_usability_controls_and_responsive_navbar(self, client: FlaskClient) -> None:
        with (
            patch("dashboard.services.status_builder.get_namespace_snapshot", return_value=EMPTY_NAMESPACE_SNAPSHOT),
            patch("dashboard.services.status_builder.get_exceptions", return_value=EMPTY_EXCEPTIONS),
            patch("dashboard.routes.pages.get_container_apps_metrics", return_value=EMPTY_CONTAINER_METRICS),
        ):
            index_html = client.get("/").get_data(as_text=True)
            flows_html = client.get("/flows").get_data(as_text=True)

        assert "navbar-expand-xl" in index_html
        for html in (index_html, flows_html):
            assert 'id="refresh-error-pill"' in html
            assert 'id="toggle-auto-refresh"' in html
            assert 'data-search="' in html

        assert 'id="expand-all-groups"' in flows_html
        assert 'id="collapse-all-groups"' in flows_html

    def test_exceptions_and_messages_enhanced_filtering(self, client: FlaskClient) -> None:
        sample_exceptions = [
            {
                "timestamp": "2026-11-27T09:00:00Z",
                "app": "phw-hl7-server",
                "type": "TimeoutError",
                "message": "Socket timed out",
                "severity": 2,
                "operation_id": "abc123",
            }
        ]
        with (
            patch("dashboard.services.azure_monitor.get_exceptions", return_value=sample_exceptions),
            patch("dashboard.routes.pages.get_exceptions", return_value=sample_exceptions),
        ):
            exc_html = client.get("/exceptions").get_data(as_text=True)

        assert 'id="exc-search"' in exc_html
        assert 'data-sev-kpi="all"' in exc_html
        assert "kpi-card--active" in exc_html
        assert 'data-search="phw-hl7-server timeouterror socket timed out abc123"' in exc_html

        sample_messages = [
            {
                "timestamp": "2026-11-27T09:00:00Z",
                "event": "MESSAGE_SENT",
                "app": "phw-sender",
                "dimensions": {"queue": "post-phw-transform"},
            }
        ]
        with patch("dashboard.routes.pages.cache.cached_nowait", return_value=sample_messages):
            msg_html = client.get("/messages").get_data(as_text=True)
        assert "row.textContent" in msg_html
        assert "post-phw-transform" in msg_html

    def test_dashboard_js_formats_timestamp_consistently_and_tracks_pause(self) -> None:
        js_path = Path(app_module.__file__).resolve().parent / "static" / "js" / "dashboard.js"
        js = js_path.read_text(encoding="utf-8")
        assert "toLocaleTimeString()" not in js
        assert "formatRefreshedAt(data.refreshed_at)" in js
        assert "setRefreshError(true)" in js
        assert "window.setAllFlowGroups" in js

    def test_html_lang_and_i18n_reflect_session_language(self, client: FlaskClient) -> None:
        with (
            patch("dashboard.services.status_builder.get_namespace_snapshot", return_value=EMPTY_NAMESPACE_SNAPSHOT),
            patch("dashboard.services.status_builder.get_exceptions", return_value=EMPTY_EXCEPTIONS),
        ):
            en_html = client.get("/").get_data(as_text=True)
            with client.session_transaction() as sess:
                sess["lang"] = "cy"
            cy_html = client.get("/").get_data(as_text=True)

        assert '<html lang="en">' in en_html
        assert '<html lang="cy">' in cy_html
        assert "window.DASHBOARD_I18N" in cy_html

    def test_accessibility_modal_flow_groups_and_reduced_motion(self, client: FlaskClient) -> None:
        with (
            patch("dashboard.services.status_builder.get_namespace_snapshot", return_value=EMPTY_NAMESPACE_SNAPSHOT),
            patch("dashboard.services.status_builder.get_exceptions", return_value=EMPTY_EXCEPTIONS),
            patch("dashboard.routes.pages.get_container_apps_metrics", return_value=EMPTY_CONTAINER_METRICS),
        ):
            flows_html = client.get("/flows").get_data(as_text=True)

        assert "backdrop.setAttribute('aria-hidden', 'false')" in flows_html
        assert "e.key === 'Escape'" in flows_html
        assert "e.key === 'Tab'" in flows_html
        assert "aria-expanded=" in flows_html
        assert "event.preventDefault();toggleFlowGroup(this);" in flows_html

        css_path = Path(app_module.__file__).resolve().parent / "static" / "css" / "style.css"
        css = css_path.read_text(encoding="utf-8")
        assert "@media (prefers-reduced-motion: reduce)" in css

        js_path = Path(app_module.__file__).resolve().parent / "static" / "js" / "dashboard.js"
        js = js_path.read_text(encoding="utf-8")
        assert "window.DASHBOARD_I18N" in js
        assert 'header.setAttribute("aria-expanded"' in js
        assert "prefersReducedMotion()" in js
        assert "expandHashTarget" in js
        assert 'window.addEventListener("hashchange", expandHashTarget)' in js

    def test_chart_redraw_edge_cases(self) -> None:
        js_dir = Path(app_module.__file__).resolve().parent / "static" / "js"

        app_history_js = (js_dir / "app-history.js").read_text(encoding="utf-8")
        assert "canvas.dataset.cssHeight" in app_history_js

        for filename in ("hl7-throughput-chart.js", "sb-chart.js"):
            chart_js = (js_dir / filename).read_text(encoding="utf-8")
            assert "fetchState = 'error'" in chart_js
            assert "if (fetchState === 'error')" in chart_js

    def test_no_easter_eggs_rendered_or_bundled(self, client: FlaskClient) -> None:
        pkg_dir = Path(app_module.__file__).resolve().parent
        for removed in (
            pkg_dir / "static" / "js" / "enhanced-ui.js",
            pkg_dir / "static" / "js" / "alternate_ui.js",
            pkg_dir / "static" / "vendor" / "threejs",
            pkg_dir / "templates" / "flows_config.html",
            pkg_dir / "templates" / "SB_Emulator_MC.html",
        ):
            assert not removed.exists(), f"Expected easter egg asset {removed} to be removed"

        with (
            patch("dashboard.services.status_builder.get_namespace_snapshot", return_value=EMPTY_NAMESPACE_SNAPSHOT),
            patch("dashboard.services.status_builder.get_exceptions", return_value=EMPTY_EXCEPTIONS),
            patch("dashboard.routes.pages.get_container_apps_metrics", return_value=EMPTY_CONTAINER_METRICS),
        ):
            pages = [("/", client.get("/")), ("/flows", client.get("/flows"))]
        with patch("dashboard.routes.pages.cache.cached_nowait", return_value=EMPTY_NAMESPACE_SNAPSHOT):
            pages.append(("/service-bus", client.get("/service-bus")))

        for route, resp in pages:
            assert resp.status_code == 200
            html = resp.get_data(as_text=True)
            for marker in ("lego-panel", "enhanced-ui.js", "alternate_ui.js", "lamp-modal", "mc-modal"):
                assert marker not in html, f"Unexpected easter egg marker {marker!r} on {route}"
