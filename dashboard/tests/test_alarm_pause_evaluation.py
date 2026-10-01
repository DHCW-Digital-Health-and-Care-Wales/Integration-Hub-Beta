"""
Evaluator tests: pause records gate Alarms 1, 2 and 3.

These cover the acceptance criteria end-to-end at the service level:
  * an active pause returns status ``paused`` and sends no alert email
  * a scheduled pause that has not started yet does not suppress anything
  * once a pause has ended (or been cancelled) alerts are raised again
Log Analytics, Cosmos state and email sending are mocked; pause records are built
relative to the real clock because the evaluators call ``datetime.now`` directly.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from dashboard.services import alarm1, alarm2, alarm3

WORKFLOW = "phw-to-mpi"


def _pause(start_offset: timedelta, end_offset: timedelta | None, scope: str = "flows") -> dict[str, Any]:
    """A stored pause record covering WORKFLOW, positioned relative to now."""
    now = datetime.now(timezone.utc)
    return {
        "pause_id": "p1",
        "scope_type": scope,
        "targets": [WORKFLOW] if scope == "flows" else [],
        "start_at": (now + start_offset).isoformat(),
        "end_at": (now + end_offset).isoformat() if end_offset is not None else None,
        "reason": "Planned maintenance",
        "requested_by": "Gareth",
        "cancelled_at": None,
    }


ACTIVE = _pause(-timedelta(hours=1), timedelta(hours=1))
ACTIVE_ALL_INDEFINITE = _pause(-timedelta(hours=1), None, scope="all")
SCHEDULED = _pause(timedelta(hours=2), timedelta(hours=3))
ENDED = _pause(-timedelta(hours=3), -timedelta(minutes=1))


def _threshold_cfg() -> dict[str, Any]:
    return {
        "alarm_enabled": True,
        "workflow_id": WORKFLOW,
        "day_threshold_minutes": 1,
        "evening_threshold_minutes": 1,
        "weekend_threshold_minutes": 1,
        "alerting_gap_minutes": 60,
        "email_alerts_enabled": True,
    }


@pytest.fixture()
def alarm1_env() -> Generator[MagicMock, None, None]:
    """Alarm 1 with one rule whose workflow has been silent for a day (i.e. in alarm)."""
    stale = datetime.now(timezone.utc) - timedelta(days=1)
    with ExitStack() as stack:
        stack.enter_context(
            patch.object(alarm1, "load_alarm_config", return_value={"rules": {"r1": _threshold_cfg()}})
        )
        stack.enter_context(patch.object(alarm1, "get_last_message_times_by_workflow", return_value={WORKFLOW: stale}))
        stack.enter_context(patch.object(alarm1, "_load_alarm_state", return_value={"rules": {}}))
        stack.enter_context(patch.object(alarm1, "_save_alarm_state"))
        yield stack.enter_context(patch.object(alarm1, "_send_alarm_email"))


@pytest.fixture()
def alarm2_env() -> Generator[MagicMock, None, None]:
    """Alarm 2 with one custom rule whose workflow has sent nothing for a day."""
    stale = datetime.now(timezone.utc) - timedelta(days=1)
    with ExitStack() as stack:
        stack.enter_context(
            patch.object(alarm2, "load_alarm2_config", return_value={"rules": {"custom-outgoing": _threshold_cfg()}})
        )
        stack.enter_context(patch.object(alarm2, "get_last_sent_times_by_workflow", return_value={WORKFLOW: stale}))
        stack.enter_context(patch.object(alarm2, "_load_alarm2_state", return_value={"rules": {}}))
        stack.enter_context(patch.object(alarm2, "_save_alarm2_state"))
        yield stack.enter_context(patch.object(alarm2, "_send_alarm2_email"))


@pytest.fixture()
def alarm3_env() -> Generator[MagicMock, None, None]:
    """Alarm 3 with one custom rule whose failure count is over threshold."""
    cfg = {"alarm_enabled": True, "workflow_id": WORKFLOW, "threshold": 1, "email_alerts_enabled": True}
    with ExitStack() as stack:
        stack.enter_context(
            patch.object(alarm3, "load_alarm3_config", return_value={"rules": {"custom-failures": cfg}})
        )
        stack.enter_context(patch.object(alarm3, "get_failure_counts", return_value={"custom-failures": 10}))
        stack.enter_context(patch.object(alarm3, "_load_alarm3_state", return_value={"rules": {}}))
        stack.enter_context(patch.object(alarm3, "_save_alarm3_state"))
        yield stack.enter_context(patch.object(alarm3, "_send_alarm3_email"))


def _evaluate_alarm1(pauses: list[dict[str, Any]]) -> dict[str, Any]:
    with patch.object(alarm1.alarm_pauses, "list_pauses", return_value=pauses):
        return alarm1.get_alarm_status()[0]


class TestAlarm1PauseGating:
    def test_no_pause_raises_alarm_and_emails(self, alarm1_env: MagicMock) -> None:
        row = _evaluate_alarm1([])
        assert row["status"] == "critical"
        alarm1_env.assert_called_once()
        assert row["scheduled_pause"] is None

    def test_active_pause_suppresses_alarm_and_email(self, alarm1_env: MagicMock) -> None:
        row = _evaluate_alarm1([ACTIVE])
        assert row["status"] == "paused"
        assert row["pause_id"] == "p1"
        assert row["paused_by"] == "Gareth"
        assert row["pause_indefinite"] is False
        alarm1_env.assert_not_called()

    def test_indefinite_all_flows_pause_suppresses_alarm(self, alarm1_env: MagicMock) -> None:
        row = _evaluate_alarm1([ACTIVE_ALL_INDEFINITE])
        assert row["status"] == "paused"
        assert row["pause_indefinite"] is True
        assert row["pause_scope"] == "all"
        alarm1_env.assert_not_called()

    def test_scheduled_pause_does_not_suppress_before_start(self, alarm1_env: MagicMock) -> None:
        row = _evaluate_alarm1([SCHEDULED])
        assert row["status"] == "critical"
        alarm1_env.assert_called_once()
        assert row["scheduled_pause"]["pause_id"] == "p1"

    def test_alarm_resumes_after_pause_ends(self, alarm1_env: MagicMock) -> None:
        row = _evaluate_alarm1([ENDED])
        assert row["status"] == "critical"
        alarm1_env.assert_called_once()


class TestAlarm2PauseGating:
    def test_active_pause_suppresses_alarm_and_email(self, alarm2_env: MagicMock) -> None:
        with patch.object(alarm2.alarm_pauses, "list_pauses", return_value=[ACTIVE]):
            row = next(r for r in alarm2.get_alarm2_status() if r["id"] == "custom-outgoing")
        assert row["status"] == "paused"
        alarm2_env.assert_not_called()

    def test_ended_pause_raises_alarm(self, alarm2_env: MagicMock) -> None:
        with patch.object(alarm2.alarm_pauses, "list_pauses", return_value=[ENDED]):
            row = next(r for r in alarm2.get_alarm2_status() if r["id"] == "custom-outgoing")
        assert row["status"] == "critical"
        alarm2_env.assert_called_once()


class TestAlarm3PauseGating:
    def test_active_pause_suppresses_alarm_and_email(self, alarm3_env: MagicMock) -> None:
        with patch.object(alarm3.alarm_pauses, "list_pauses", return_value=[ACTIVE]):
            row = next(r for r in alarm3.get_alarm3_status() if r["id"] == "custom-failures")
        assert row["status"] == "paused"
        alarm3_env.assert_not_called()

    def test_scheduled_pause_raises_alarm(self, alarm3_env: MagicMock) -> None:
        with patch.object(alarm3.alarm_pauses, "list_pauses", return_value=[SCHEDULED]):
            row = next(r for r in alarm3.get_alarm3_status() if r["id"] == "custom-failures")
        assert row["status"] == "critical"
        assert row["scheduled_pause"]["pause_id"] == "p1"
        alarm3_env.assert_called_once()
