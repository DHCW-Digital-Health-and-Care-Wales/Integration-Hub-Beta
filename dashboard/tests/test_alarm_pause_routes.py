"""
Route tests for the alarm pause endpoints in dashboard.routes.alarms.

Covers the JSON create/cancel/list/options APIs, the legacy single-rule
``/alarmN/pause`` and ``/alarmN/unpause`` endpoints (now backed by pause records),
the HTTP status mapping for each pause error, and rendering of the Alarm Pauses page
and the pause indicator on the overview pages.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import patch

import pytest
from flask.testing import FlaskClient

from dashboard import app as app_module
from dashboard.routes import alarms as alarms_routes
from dashboard.services import alarm_pauses, cache

app = app_module.app

FLOWS: dict[str, dict[str, Any]] = {"phw-to-mpi": {"label": "PHW → MPI"}}
CFG1 = [{"id": "phw-inactivity", "display_name": "PHW Inactivity", "workflow_id": "phw-to-mpi"}]


@pytest.fixture()
def client() -> Generator[FlaskClient, None, None]:
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def _stub_rule_catalogue() -> Generator[None, None, None]:
    """Keep route tests offline: fixed flows and rule configs, no Cosmos pauses by default."""
    with (
        patch("dashboard.routes.alarms.get_flows", return_value=FLOWS),
        patch("dashboard.routes.alarms.get_config_page_data", return_value=CFG1),
        patch("dashboard.routes.alarms.get_alarm2_config_page_data", return_value=[]),
        patch("dashboard.routes.alarms.get_alarm3_config_page_data", return_value=[]),
    ):
        yield


def _stored_pause(pause_id: str = "p1", start_offset: timedelta = -timedelta(hours=1)) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {
        "pause_id": pause_id,
        "scope_type": "flows",
        "targets": ["phw-to-mpi"],
        "start_at": (now + start_offset).isoformat(),
        "end_at": (now + timedelta(hours=2)).isoformat(),
        "reason": "Upgrade",
        "requested_by": "Alphy",
        "created_at": now.isoformat(),
        "cancelled_at": None,
    }


class TestCreatePauseApi:
    def test_create_returns_201_with_pause(self, client: FlaskClient) -> None:
        view = {"pause_id": "new", "status": "scheduled"}
        with patch.object(alarm_pauses, "create_pause", return_value=view) as mock_create:
            response = client.post("/api/alarm-pauses", json={"scope_type": "all", "reason": "x", "requested_by": "y"})
        assert response.status_code == 201
        assert response.get_json() == {"ok": True, "pause": view}
        # Known rules are passed through for rule-scope validation.
        assert mock_create.call_args[0][1]["alarm1"] == {"phw-inactivity": "phw-to-mpi"}

    def test_non_object_body_is_rejected(self, client: FlaskClient) -> None:
        response = client.post("/api/alarm-pauses", json=["not", "an", "object"])
        assert response.status_code == 400

    def test_validation_error_returns_400(self, client: FlaskClient) -> None:
        response = client.post("/api/alarm-pauses", json={"scope_type": "all", "reason": "", "requested_by": "y"})
        assert response.status_code == 400
        assert response.get_json() == {"ok": False, "error": "Reason is required."}

    def test_unconfigured_persistence_returns_503(self, client: FlaskClient) -> None:
        # conftest disables Cosmos, so a valid request cannot be stored.
        response = client.post(
            "/api/alarm-pauses",
            json={"scope_type": "all", "end_mode": "indefinite", "reason": "x", "requested_by": "y"},
        )
        assert response.status_code == 503
        assert response.get_json()["ok"] is False


class TestCancelPauseApi:
    def test_cancel_returns_updated_pause(self, client: FlaskClient) -> None:
        with patch.object(alarm_pauses, "cancel_pause", return_value={"pause_id": "p1", "status": "cancelled"}):
            response = client.post("/api/alarm-pauses/p1/cancel")
        assert response.status_code == 200
        assert response.get_json()["pause"]["status"] == "cancelled"

    def test_unknown_pause_returns_404(self, client: FlaskClient) -> None:
        not_found = alarm_pauses.PauseNotFoundError("Pause not found.")
        with patch.object(alarm_pauses, "cancel_pause", side_effect=not_found):
            response = client.post("/api/alarm-pauses/missing/cancel")
        assert response.status_code == 404


class TestLegacyRuleEndpoints:
    def test_pause_now_passes_duration_and_required_fields(self, client: FlaskClient) -> None:
        with patch("dashboard.routes.alarms.pause_alarm_rule", return_value={"pause_id": "p"}) as mock_pause:
            response = client.post(
                "/alarm1/pause/phw-inactivity",
                json={"duration_minutes": 30, "reason": "Fix", "requested_by": "Matt"},
            )
        assert response.status_code == 200
        mock_pause.assert_called_once_with("phw-inactivity", 30, "Fix", "Matt")

    def test_pause_now_indefinite_ignores_duration(self, client: FlaskClient) -> None:
        with patch("dashboard.routes.alarms.pause_alarm2_rule", return_value={}) as mock_pause:
            client.post(
                "/alarm2/pause/r",
                json={"indefinite": True, "duration_minutes": 30, "reason": "Fix", "requested_by": "Matt"},
            )
        assert mock_pause.call_args[0][1] is None

    def test_pause_now_rejects_non_numeric_duration(self, client: FlaskClient) -> None:
        response = client.post("/alarm3/pause/r", json={"duration_minutes": "soon"})
        assert response.status_code == 400

    @pytest.mark.parametrize("body", [[1], "text", 5])
    def test_pause_now_rejects_non_object_json(self, client: FlaskClient, body: object) -> None:
        with patch("dashboard.routes.alarms.pause_alarm_rule") as mock_pause:
            response = client.post("/alarm1/pause/phw-inactivity", json=body)
        assert response.status_code == 400
        assert response.get_json()["error"] == "Expected a JSON object."
        mock_pause.assert_not_called()

    def test_pause_now_without_reason_is_rejected(self, client: FlaskClient) -> None:
        # Unpatched pause_alarm_rule: validation runs for real against the alarm's own rule list.
        with patch("dashboard.services.alarm1.get_config_page_data", return_value=CFG1):
            response = client.post("/alarm1/pause/phw-inactivity", json={"duration_minutes": 30, "requested_by": "M"})
        assert response.status_code == 400
        assert response.get_json()["error"] == "Reason is required."

    def test_unpause_success(self, client: FlaskClient) -> None:
        with patch("dashboard.routes.alarms.unpause_alarm_rule") as mock_resume:
            response = client.post("/alarm1/unpause/phw-inactivity")
        assert response.status_code == 200
        mock_resume.assert_called_once_with("phw-inactivity")

    def test_unpause_when_storage_unavailable_returns_503(self, client: FlaskClient) -> None:
        # Unpatched resume path; conftest disables Cosmos so the pause read fails.
        with patch("dashboard.services.alarm1.get_config_page_data", return_value=CFG1):
            response = client.post("/alarm1/unpause/phw-inactivity")
        assert response.status_code == 503
        assert response.get_json()["ok"] is False

    def test_unpause_under_wider_pause_returns_409_with_manage_url(self, client: FlaskClient) -> None:
        conflict = alarm_pauses.PauseConflictError("Wider pause", "p9")
        with patch("dashboard.routes.alarms.unpause_alarm3_rule", side_effect=conflict):
            response = client.post("/alarm3/unpause/r")
        assert response.status_code == 409
        body = response.get_json()
        assert body["pause_id"] == "p9"
        assert body["manage_url"] == "/alarms/pauses#pause-p9"


class TestPatchCachedRows:
    def test_applies_active_pause_and_clears_ended_one(self) -> None:
        rows = [
            {"id": "phw-inactivity", "workflow_id": "phw-to-mpi", "status": "critical"},
            {"id": "other", "workflow_id": "pims-to-mpi", "status": "paused", "pause_id": "gone"},
        ]
        with cache.cache_lock:
            saved = dict(cache.cache_data["alarms"])
            cache.cache_data["alarms"] = {"data": rows, "ts": 123.0}
        try:
            with patch.object(alarm_pauses, "list_pauses", return_value=[_stored_pause()]):
                alarms_routes._patch_cached_rows()
            patched = {r["id"]: r for r in cache.cache_data["alarms"]["data"]}
            assert patched["phw-inactivity"]["status"] == "paused"
            assert patched["phw-inactivity"]["pause_id"] == "p1"
            assert patched["other"]["status"] == "unknown"
            assert patched["other"]["pause_id"] is None
            # Marked stale so a background refresh re-evaluates the true status.
            assert cache.cache_data["alarms"]["ts"] == 0.0
        finally:
            with cache.cache_lock:
                cache.cache_data["alarms"] = saved


class TestPausePagesAndListing:
    def test_list_and_options_endpoints(self, client: FlaskClient) -> None:
        with patch.object(alarm_pauses, "list_pauses", return_value=[_stored_pause()]):
            listing = client.get("/api/alarm-pauses").get_json()
            options = client.get("/api/alarm-pauses/options").get_json()
        assert listing["summary"] == {"active": 1, "scheduled": 0}
        assert listing["groups"]["active"][0]["target_labels"] == ["PHW → MPI"]
        assert options["flow_options"] == [{"id": "phw-to-mpi", "label": "PHW → MPI"}]
        assert options["rule_options"][0]["label"] == "Inactivity: PHW Inactivity"

    def test_pauses_page_renders_empty_state(self, client: FlaskClient) -> None:
        response = client.get("/alarms/pauses")
        assert response.status_code == 200
        assert b"No alarms are paused." in response.data
        assert b"No pauses are scheduled." in response.data
        # Cosmos is disabled in tests, so the page warns that pauses can't be created.
        assert b"pauses cannot be created" in response.data

    def test_pauses_page_lists_active_and_scheduled(self, client: FlaskClient) -> None:
        pauses = [_stored_pause("act"), _stored_pause("sch", start_offset=timedelta(hours=1))]
        with patch.object(alarm_pauses, "list_pauses", return_value=pauses):
            response = client.get("/alarms/pauses")
        assert b'id="pause-act"' in response.data
        assert b'id="pause-sch"' in response.data
        assert b'data-pause-cancel="sch" data-pause-status="scheduled"' in response.data
        assert b"Alphy" in response.data

    def test_alarms_overview_shows_pause_indicator(self, client: FlaskClient) -> None:
        with (
            patch("dashboard.routes.alarms.cache.multi_cached_nowait", return_value=([], [], [])),
            patch.object(alarm_pauses, "list_pauses", return_value=[_stored_pause()]),
        ):
            response = client.get("/alarms")
        assert response.status_code == 200
        assert b'id="pause-indicator"' in response.data
        assert b'<span id="pause-indicator-active">1</span>' in response.data

    def test_alarms_status_api_includes_pause_summary(self, client: FlaskClient) -> None:
        with (
            patch("dashboard.routes.api.cache.multi_cached_nowait", return_value=([], [], [])),
            patch.object(alarm_pauses, "list_pauses", return_value=[_stored_pause(start_offset=timedelta(hours=1))]),
        ):
            body = client.get("/api/alarms/status").get_json()
        assert body["pause_summary"] == {"active": 0, "scheduled": 1}

    def test_overview_shows_pause_indicator_in_page_header(self, client: FlaskClient) -> None:
        with (
            patch("dashboard.routes.pages.get_cached_status", return_value={"kpis": {}, "flows": []}),
            patch("dashboard.routes.pages.render_template", return_value="") as mock_render,
            patch.object(alarm_pauses, "list_pauses", return_value=[_stored_pause()]),
        ):
            client.get("/")
        assert mock_render.call_args.kwargs["pause_summary"] == {"active": 1, "scheduled": 0}
        template = app.jinja_env.loader.get_source(app.jinja_env, "index.html")[0]  # type: ignore[union-attr]
        # The indicator must sit in the page header, above the KPI strip and the Alarms section.
        assert template.index("pause_indicator(pause_summary)") < template.index('id="kpi-strip"')

    def test_status_api_includes_pause_summary_for_live_header(self, client: FlaskClient) -> None:
        with (
            patch("dashboard.routes.api.get_cached_status", return_value={}),
            patch("dashboard.routes.api.cache.multi_cached_nowait", return_value=([{"status": "paused"}], [], [])),
            patch.object(alarm_pauses, "list_pauses", return_value=[_stored_pause()]),
        ):
            body = client.get("/api/status").get_json()
        assert body["pause_summary"] == {"active": 1, "scheduled": 0}
        assert body["alarm1_summary"]["paused"] == 1
