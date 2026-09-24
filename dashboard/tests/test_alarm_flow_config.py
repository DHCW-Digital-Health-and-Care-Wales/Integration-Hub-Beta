"""Tests for the per-flow alarm configuration screen (``/alarms/config``)."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from flask.testing import FlaskClient
from werkzeug.datastructures import MultiDict

from dashboard import app as app_module
from dashboard.routes import alarm_config

app = app_module.app

FLOWS: dict[str, dict[str, Any]] = {
    "phw-to-mpi": {"label": "PHW → MPI"},
    "pims-to-mpi": {"label": "PIMS → MPI"},
}

A1_RULES: list[dict[str, Any]] = [
    {"id": "phw-to-mpi", "display_name": "PHW Inactivity", "workflow_id": "phw-to-mpi", "alarm_enabled": True,
     "day_threshold_minutes": 60, "evening_threshold_minutes": 120, "weekend_threshold_minutes": 240,
     "alerting_gap_minutes": 60, "email_alerts_enabled": False, "email_ooh_enabled": False},
    {"id": "pims-to-mpi", "display_name": "PIMS Inactivity", "workflow_id": "pims-to-mpi", "alarm_enabled": True,
     "day_threshold_minutes": 60, "evening_threshold_minutes": 120, "weekend_threshold_minutes": 240,
     "alerting_gap_minutes": 60, "email_alerts_enabled": False, "email_ooh_enabled": False},
]
A3_RULES: list[dict[str, Any]] = [
    {"id": "phw-to-mpi-failures", "display_name": "PHW Failures", "workflow_id": "phw-to-mpi",
     "alarm_enabled": False, "window_duration_minutes": 15, "threshold": 1, "alerting_gap_minutes": 60,
     "email_alerts_enabled": False, "email_ooh_enabled": False},
]


@pytest.fixture()
def client() -> Generator[FlaskClient, None, None]:
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture()
def saves() -> Generator[dict[int, MagicMock], None, None]:
    """Stub config reads with fixed rules and capture every save call per alarm type."""
    mocks = {1: MagicMock(), 2: MagicMock(), 3: MagicMock()}
    with (
        patch("dashboard.routes.alarm_config.get_flows", return_value=FLOWS),
        patch("dashboard.routes.alarm_config.get_config_page_data", return_value=A1_RULES),
        patch("dashboard.routes.alarm_config.get_alarm2_config_page_data", return_value=[]),
        patch("dashboard.routes.alarm_config.get_alarm3_config_page_data", return_value=A3_RULES),
        patch("dashboard.routes.alarm_config.load_alarm_config", side_effect=lambda: {"rules": {}}),
        patch("dashboard.routes.alarm_config.load_alarm2_config", side_effect=lambda: {"rules": {}}),
        patch("dashboard.routes.alarm_config.load_alarm3_config", side_effect=lambda: {"rules": {}}),
        patch("dashboard.routes.alarm_config.save_alarm_config", mocks[1]),
        patch("dashboard.routes.alarm_config.save_alarm2_config", mocks[2]),
        patch("dashboard.routes.alarm_config.save_alarm3_config", mocks[3]),
    ):
        yield mocks


class TestFlowConfigPageGet:
    def test_no_flow_shows_prompt(self, client: FlaskClient, saves: dict[int, MagicMock]) -> None:
        response = client.get("/alarms/config")
        assert response.status_code == 200
        assert b"Select a flow to configure its alarms." in response.data
        assert b'data-flow-id="phw-to-mpi"' in response.data
        assert b'id="flow-config-form"' not in response.data

    def test_selected_flow_shows_only_its_rules_for_all_alarm_types(
        self, client: FlaskClient, saves: dict[int, MagicMock]
    ) -> None:
        response = client.get("/alarms/config?flow=phw-to-mpi")
        assert response.status_code == 200
        assert b'id="a1-rule-phw-to-mpi"' in response.data
        assert b'id="a3-rule-phw-to-mpi-failures"' in response.data
        assert b"PIMS Inactivity" not in response.data
        # Alarm 2 has no rules for this flow.
        assert b"No Alarm 2 rules are configured for this flow." in response.data
        assert b'action="/alarms/config?flow=phw-to-mpi"' in response.data

    def test_add_panels_are_scoped_to_flow_and_disabled_until_opened(
        self, client: FlaskClient, saves: dict[int, MagicMock]
    ) -> None:
        response = client.get("/alarms/config?flow=phw-to-mpi")
        for prefix in (b"a1-", b"a2-", b"a3-"):
            assert b'name="' + prefix + b'new_workflow_id" value="phw-to-mpi" disabled' in response.data

    @pytest.mark.parametrize(
        ("prefix", "marker"),
        [("a1-", b"MESSAGE_RECEIVED"), ("a2-", b"messages_sent"), ("a3-", b"Lookback Window")],
    )
    def test_each_alarm_section_has_help_button_and_panel(
        self, client: FlaskClient, saves: dict[int, MagicMock], prefix: str, marker: bytes
    ) -> None:
        response = client.get("/alarms/config?flow=phw-to-mpi")
        html = response.data
        assert f'data-bs-target="#{prefix}help"'.encode() in html
        # Panels follow the form, so each chunk after a split holds exactly one panel.
        chunks = html.split(b'<div class="offcanvas offcanvas-end')
        panel = next(c for c in chunks[1:] if f'id="{prefix}help"'.encode() in c)
        assert b"What it does" in panel
        assert b"How to configure" in panel
        assert marker in panel

    def test_help_panels_absent_without_selected_flow(
        self, client: FlaskClient, saves: dict[int, MagicMock]
    ) -> None:
        assert b'id="a1-help"' not in client.get("/alarms/config").data

    def test_email_switch_disabled_when_email_not_configured(
        self, client: FlaskClient, saves: dict[int, MagicMock]
    ) -> None:
        with patch("dashboard.routes.alarm_config.email_alerts_configured", return_value=False):
            response = client.get("/alarms/config?flow=phw-to-mpi")
        assert b"Configure SMTP in .env to enable" in response.data

    def test_custom_workflow_id_is_accepted_as_new_flow(
        self, client: FlaskClient, saves: dict[int, MagicMock]
    ) -> None:
        response = client.get("/alarms/config?flow=new-flow_1")
        assert response.status_code == 200
        assert b"is not a discovered flow" in response.data
        assert b'id="flow-config-form"' in response.data

    @pytest.mark.parametrize("bad_id", ["-leading-dash", "has space", "a" * 121, "x'or'1", "dotted.id"])
    def test_invalid_workflow_id_is_rejected(
        self, client: FlaskClient, saves: dict[int, MagicMock], bad_id: str
    ) -> None:
        response = client.get("/alarms/config", query_string={"flow": bad_id})
        assert response.status_code == 200
        assert b"Invalid workflow ID." in response.data
        assert b'id="flow-config-form"' not in response.data


class TestFlowConfigPagePost:
    def test_post_without_valid_flow_is_rejected(self, client: FlaskClient, saves: dict[int, MagicMock]) -> None:
        assert client.post("/alarms/config", data={"a1-alerting_gap_x": "5"}).status_code == 400
        assert client.post("/alarms/config?flow=bad%20id", data={}).status_code == 400
        assert not any(m.called for m in saves.values())

    def test_only_submitted_alarm_types_are_saved(self, client: FlaskClient, saves: dict[int, MagicMock]) -> None:
        response = client.post(
            "/alarms/config?flow=phw-to-mpi",
            data={"a3-alerting_gap_phw-to-mpi-failures": "30", "a3-workflow_id_phw-to-mpi-failures": "phw-to-mpi",
                  "a3-threshold_phw-to-mpi-failures": "4", "a3-window_duration_phw-to-mpi-failures": "10"},
        )
        assert response.status_code == 200
        assert b"Configuration saved successfully." in response.data
        assert not saves[1].called and not saves[2].called
        rule = saves[3].call_args[0][0]["rules"]["phw-to-mpi-failures"]
        assert rule["threshold"] == 4
        assert rule["window_duration_minutes"] == 10
        assert rule["alerting_gap_minutes"] == 30
        assert rule["workflow_id"] == "phw-to-mpi"

    def test_add_rule_uses_selected_flow_and_highlights_it(
        self, client: FlaskClient, saves: dict[int, MagicMock]
    ) -> None:
        response = client.post(
            "/alarms/config?flow=pims-to-mpi",
            data={"a2-new_workflow_id": "pims-to-mpi", "a2-new_enabled": "on", "a2-new_day_threshold": "30"},
        )
        assert response.status_code == 200
        rules = saves[2].call_args[0][0]["rules"]
        assert len(rules) == 1
        (new_rid, new_rule), = rules.items()
        assert new_rule["workflow_id"] == "pims-to-mpi"
        assert new_rule["alarm_enabled"] is True
        assert new_rule["day_threshold_minutes"] == 30
        assert f'"a2-rule-{new_rid}"'.encode() in response.data

    def test_same_rule_id_across_alarm_types_does_not_collide(
        self, client: FlaskClient, saves: dict[int, MagicMock]
    ) -> None:
        client.post(
            "/alarms/config?flow=phw-to-mpi",
            data={"a1-alerting_gap_shared": "11", "a1-workflow_id_shared": "phw-to-mpi",
                  "a2-alerting_gap_shared": "22", "a2-workflow_id_shared": "phw-to-mpi"},
        )
        assert saves[1].call_args[0][0]["rules"]["shared"]["alerting_gap_minutes"] == 11
        assert saves[2].call_args[0][0]["rules"]["shared"]["alerting_gap_minutes"] == 22
        assert not saves[3].called

    def test_delete_marks_rule_deleted_and_skips_update(
        self, client: FlaskClient, saves: dict[int, MagicMock]
    ) -> None:
        client.post(
            "/alarms/config?flow=phw-to-mpi",
            data={"a1-delete_phw-to-mpi": "1", "a1-alerting_gap_phw-to-mpi": "99"},
        )
        rule = saves[1].call_args[0][0]["rules"]["phw-to-mpi"]
        assert rule == {"deleted": True}


class TestLegacyConfigRedirects:
    @pytest.mark.parametrize("url", ["/alarm-config", "/alarm2-config", "/alarm3-config"])
    def test_legacy_urls_redirect_to_flow_config(self, client: FlaskClient, url: str) -> None:
        response = client.get(url)
        assert response.status_code == 302
        assert response.headers["Location"] == "/alarms/config"

    def test_legacy_redirect_preserves_flow(self, client: FlaskClient) -> None:
        response = client.get("/alarm2-config?flow=phw-to-mpi")
        assert response.headers["Location"] == "/alarms/config?flow=phw-to-mpi"


class TestScopedForm:
    def test_strips_prefix_and_ignores_other_alarm_types(self) -> None:
        form = MultiDict([("a1-enabled_x", "on"), ("a2-enabled_x", "on"), ("flow", "f")])
        assert dict(alarm_config._scoped_form(form, "a1-")) == {"enabled_x": "on"}

    def test_empty_form_returns_empty(self) -> None:
        assert not alarm_config._scoped_form(MultiDict(), "a1-")
