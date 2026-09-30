"""
Local integration tests: alarm pauses against the real Cosmos DB emulator.

Unlike the unit tests, nothing in the pause/config/state storage path is mocked — pauses
are created and cancelled through the Flask routes, persisted to the emulator, read back
by the Alarm 3 evaluator, and the alert email call is captured. Only Log Analytics
(failure counts) and the outbound email transport are stubbed.

Opt-in and local-only. With the emulator running and ``COSMOS_*`` set in ``dashboard/.env``::

    docker compose --profile dashboard up -d cosmos-emulator    # from local/
    RUN_COSMOS_EMULATOR_TESTS=1 uv run pytest tests/test_alarm_pause_emulator.py -v

Each test uses a unique throwaway flow id and removes its rule, state and pauses afterwards.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Generator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock, patch
from urllib.parse import urlparse

import pytest
from flask.testing import FlaskClient

from dashboard import app as app_module
from dashboard import config
from dashboard.services import alarm3, alarm_pauses, cosmos_store

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_COSMOS_EMULATOR_TESTS") != "1",
    reason="Set RUN_COSMOS_EMULATOR_TESTS=1 to run against the local Cosmos emulator.",
)

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "cosmos-emulator"})
FAILURE_COUNT = 5


@dataclass
class EmulatorRule:
    workflow_id: str
    rule_id: str
    display_name: str
    emails: MagicMock

    def evaluate(self) -> dict[str, Any]:
        """Run the real Alarm 3 evaluator and return this rule's status row."""
        return next(r for r in alarm3.get_alarm3_status() if r["id"] == self.rule_id)

    def emails_sent(self) -> int:
        return sum(1 for c in self.emails.call_args_list if self.display_name in c.args[0])


@pytest.fixture(autouse=True)
def _disable_cosmos() -> Generator[None, None, None]:
    """Override conftest's hermetic fixture: these tests must reach the local emulator."""
    endpoint = config.COSMOS_ENDPOINT
    if not endpoint:
        pytest.skip("COSMOS_ENDPOINT is not set.")
    if urlparse(endpoint).hostname not in _LOCAL_HOSTS:
        pytest.fail(f"Refusing to run emulator tests against non-local Cosmos endpoint: {endpoint}")
    cosmos_store._reset_client_for_tests()
    try:
        cosmos_store.query_documents(alarm_pauses.PARTITION_KEY, strict=True)
    except cosmos_store.CosmosUnavailableError:
        pytest.skip(f"Cosmos emulator is not reachable at {endpoint}.")
    yield
    cosmos_store._reset_client_for_tests()


@pytest.fixture()
def client() -> Generator[FlaskClient, None, None]:
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c


@pytest.fixture()
def rule() -> Generator[EmulatorRule, None, None]:
    """An enabled Alarm 3 rule on a throwaway flow, in alarm, with email alerts on."""
    workflow_id = f"itest-{uuid.uuid4().hex[:8]}"
    rule_id = alarm3.generate_rule_id(workflow_id, set())
    display_name = f"Emulator test {workflow_id}"

    cfg = alarm3.load_alarm3_config()
    cfg.setdefault("rules", {})[rule_id] = {
        "display_name": display_name,
        "workflow_id": workflow_id,
        "alarm_enabled": True,
        "threshold": 1,
        "window_duration_minutes": 15,
        "alerting_gap_minutes": 60,
        "email_alerts_enabled": True,
        "email_ooh_enabled": True,
    }
    alarm3.save_alarm3_config(cfg)

    now = datetime.now(timezone.utc)
    if alarm_pauses.active_pause_for(alarm_pauses.list_pauses(strict=True), "alarm3", rule_id, workflow_id, now):
        _cleanup(workflow_id, rule_id)
        pytest.skip("An active all-flows pause exists in the emulator (seed_example_alarms.py --remove clears it).")

    with (
        patch.object(alarm3, "get_failure_counts", return_value={rule_id: FAILURE_COUNT}),
        patch.object(alarm3, "send_alert_email", return_value=True) as emails,
        patch("dashboard.routes.alarms.get_flows", return_value={}),
    ):
        yield EmulatorRule(workflow_id, rule_id, display_name, emails)

    _cleanup(workflow_id, rule_id)


def _cleanup(workflow_id: str, rule_id: str) -> None:
    """Remove this test's rule, its alarm state and every pause that targets its flow or rule."""
    cfg = alarm3.load_alarm3_config()
    cfg.get("rules", {}).pop(rule_id, None)
    alarm3.save_alarm3_config(cfg)

    state = alarm3._load_alarm3_state()
    if state.get("rules", {}).pop(rule_id, None) is not None:
        alarm3._save_alarm3_state(state)

    for pause in alarm_pauses.list_pauses():
        targets = pause.get("targets") or []
        if workflow_id in targets or any(isinstance(t, dict) and t.get("rule_id") == rule_id for t in targets):
            cosmos_store.delete_document(alarm_pauses.PARTITION_KEY, pause["pause_id"])


def _create_flow_pause(client: FlaskClient, workflow_id: str, start: str | None = None) -> dict[str, Any]:
    response = client.post(
        "/api/alarm-pauses",
        json={
            "scope_type": "flows",
            "targets": [workflow_id],
            "start": start,
            "end_mode": "duration",
            "duration_minutes": 60,
            "reason": "Emulator integration test",
            "requested_by": "pytest",
        },
    )
    assert response.status_code == 201, response.get_json()
    pause: dict[str, Any] = response.get_json()["pause"]
    return pause


def _stored_pause(pause_id: str) -> dict[str, Any]:
    return next(p for p in alarm_pauses.list_pauses(strict=True) if p["pause_id"] == pause_id)


class TestBaseline:
    def test_unpaused_rule_in_alarm_sends_email(self, rule: EmulatorRule) -> None:
        # Guards the other tests: without a pause the rule must fire, or "no email" proves nothing.
        row = rule.evaluate()
        assert row["status"] == "critical"
        assert rule.emails_sent() == 1


class TestFlowPause:
    def test_flow_pause_suppresses_email_until_cancelled(self, client: FlaskClient, rule: EmulatorRule) -> None:
        pause = _create_flow_pause(client, rule.workflow_id)
        assert pause["status"] == "active"

        # Fresh client so the pause is proven to come back from Cosmos, not process memory.
        cosmos_store._reset_client_for_tests()
        listed = client.get("/api/alarm-pauses").get_json()
        assert pause["pause_id"] in [p["pause_id"] for p in listed["groups"]["active"]]

        row = rule.evaluate()
        assert row["status"] == "paused"
        assert row["pause_id"] == pause["pause_id"]
        assert row["paused_by"] == "pytest"
        assert rule.emails_sent() == 0

        # A rule inside a flow pause can't be resumed on its own.
        conflict = client.post(f"/alarm3/unpause/{rule.rule_id}")
        assert conflict.status_code == 409
        assert conflict.get_json()["pause_id"] == pause["pause_id"]
        assert rule.evaluate()["status"] == "paused"

        cancelled = client.post(f"/api/alarm-pauses/{pause['pause_id']}/cancel")
        assert cancelled.status_code == 200
        assert _stored_pause(pause["pause_id"])["cancelled_at"] is not None

        assert rule.evaluate()["status"] == "critical"
        assert rule.emails_sent() == 1


class TestScheduledPause:
    def test_scheduled_pause_does_not_suppress_before_start(self, client: FlaskClient, rule: EmulatorRule) -> None:
        start = (datetime.now(alarm_pauses.LONDON_TZ) + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
        pause = _create_flow_pause(client, rule.workflow_id, start=start)
        assert pause["status"] == "scheduled"

        row = rule.evaluate()
        assert row["status"] == "critical"
        assert row["scheduled_pause"]["pause_id"] == pause["pause_id"]
        assert rule.emails_sent() == 1

    def test_cancelled_scheduled_pause_never_activates(self, client: FlaskClient, rule: EmulatorRule) -> None:
        start = (datetime.now(alarm_pauses.LONDON_TZ) + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
        pause = _create_flow_pause(client, rule.workflow_id, start=start)

        assert client.post(f"/api/alarm-pauses/{pause['pause_id']}/cancel").status_code == 200

        listed = client.get("/api/alarm-pauses").get_json()
        recent = {p["pause_id"]: p["status"] for p in listed["groups"]["recent"]}
        assert recent.get(pause["pause_id"]) == "cancelled"
        assert rule.evaluate()["scheduled_pause"] is None


class TestSingleRulePause:
    def test_pause_and_resume_round_trip(self, client: FlaskClient, rule: EmulatorRule) -> None:
        paused = client.post(
            f"/alarm3/pause/{rule.rule_id}",
            json={"duration_minutes": 30, "reason": "Emulator integration test", "requested_by": "pytest"},
        )
        assert paused.status_code == 200, paused.get_json()

        row = rule.evaluate()
        assert row["status"] == "paused"
        assert row["pause_scope"] == "rule"
        assert rule.emails_sent() == 0

        resumed = client.post(f"/alarm3/unpause/{rule.rule_id}")
        assert resumed.status_code == 200, resumed.get_json()

        assert rule.evaluate()["status"] == "critical"
        assert rule.emails_sent() == 1
