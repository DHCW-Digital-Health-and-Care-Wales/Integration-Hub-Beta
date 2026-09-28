"""
Unit tests for dashboard.services.alarm_base — the shared Cosmos DB config/
state persistence and pause helpers used by alarm1.py, alarm2.py, and alarm3.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from dashboard.services import alarm_base


class TestLoadSaveConfig:
    def test_load_config_returns_empty_rules_when_no_document_stored(self) -> None:
        with patch("dashboard.services.alarm_base.cosmos_store.get_document", return_value=None):
            assert alarm_base.load_config("alarm1") == {"rules": {}}

    def test_load_config_defaults_missing_rules_key(self) -> None:
        with patch("dashboard.services.alarm_base.cosmos_store.get_document", return_value={"other": 1}):
            result = alarm_base.load_config("alarm1")
        assert result == {"other": 1, "rules": {}}

    def test_load_config_returns_stored_document_unchanged_when_rules_present(self) -> None:
        stored = {"rules": {"r1": {"alarm_enabled": True}}}
        with patch("dashboard.services.alarm_base.cosmos_store.get_document", return_value=stored):
            assert alarm_base.load_config("alarm2") == stored

    def test_save_config_upserts_with_partition_and_doc_id(self) -> None:
        with patch("dashboard.services.alarm_base.cosmos_store.upsert_document") as mock_upsert:
            alarm_base.save_config("alarm3", {"rules": {}}, "config")
        mock_upsert.assert_called_once_with("alarm3", "config", {"rules": {}}, doc_type="alarm_config")


class TestLoadSaveState:
    def test_load_state_returns_empty_rules_when_no_document_stored(self) -> None:
        with patch("dashboard.services.alarm_base.cosmos_store.get_document", return_value=None):
            assert alarm_base.load_state("alarm1") == {"rules": {}}

    def test_save_state_upserts_with_partition_and_doc_id(self) -> None:
        with patch("dashboard.services.alarm_base.cosmos_store.upsert_document") as mock_upsert:
            alarm_base.save_state("alarm2", {"rules": {"r1": {}}}, "state")
        mock_upsert.assert_called_once_with("alarm2", "state", {"rules": {"r1": {}}}, doc_type="alarm_state")


class TestResolvePause:
    NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)

    def _record(self, end: datetime | None) -> dict:
        return {
            "pause_id": "p1",
            "scope_type": "flows",
            "targets": ["phw-to-mpi"],
            "start_at": (self.NOW - timedelta(hours=1)).isoformat(),
            "end_at": end.isoformat() if end else None,
            "reason": "Deployment",
            "requested_by": "Yoana",
        }

    def test_active_pause_record_returns_row_fields(self) -> None:
        fields = alarm_base.resolve_pause(
            {}, "alarm1", "r1", "phw-to-mpi", [self._record(self.NOW + timedelta(minutes=30))], self.NOW
        )
        assert fields is not None
        assert fields["pause_id"] == "p1"
        assert fields["pause_remaining"] == 30
        assert fields["paused_by"] == "Yoana"
        assert set(fields) == set(alarm_base.EMPTY_PAUSE_FIELDS)

    def test_pause_on_another_flow_does_not_apply(self) -> None:
        assert alarm_base.resolve_pause({}, "alarm1", "r1", "pims-to-mpi", [self._record(None)], self.NOW) is None

    def test_legacy_paused_until_is_still_honoured(self) -> None:
        rule_state = {"paused_until": (self.NOW + timedelta(minutes=20)).isoformat(), "pause_reason": "old"}
        fields = alarm_base.resolve_pause(rule_state, "alarm1", "r1", "phw-to-mpi", [], self.NOW)
        assert fields is not None
        assert fields["pause_id"] is None
        assert fields["pause_scope"] == "rule"
        assert fields["pause_reason"] == "old"
        assert fields["pause_remaining"] == 20

    def test_expired_legacy_pause_does_not_apply(self) -> None:
        rule_state = {"paused_until": (self.NOW - timedelta(minutes=1)).isoformat()}
        assert alarm_base.resolve_pause(rule_state, "alarm1", "r1", "phw-to-mpi", [], self.NOW) is None


class TestClearExpiredLegacyPause:
    NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)

    def test_clears_expired_pause_and_keeps_other_state(self) -> None:
        state_rules = {"r1": {"paused_until": "2026-10-01T11:00:00+00:00", "pause_reason": "x", "last_alarm_at": "z"}}
        assert alarm_base.clear_expired_legacy_pause(state_rules, "r1", self.NOW) is True
        assert state_rules == {"r1": {"last_alarm_at": "z"}}

    def test_removes_rule_entry_when_it_becomes_empty(self) -> None:
        state_rules = {"r1": {"paused_until": "2026-10-01T11:00:00+00:00"}}
        assert alarm_base.clear_expired_legacy_pause(state_rules, "r1", self.NOW) is True
        assert state_rules == {}

    def test_leaves_unexpired_or_missing_pause_alone(self) -> None:
        state_rules = {"r1": {"paused_until": "2026-10-01T13:00:00+00:00"}, "r2": {"last_alarm_at": "z"}}
        assert alarm_base.clear_expired_legacy_pause(state_rules, "r1", self.NOW) is False
        assert alarm_base.clear_expired_legacy_pause(state_rules, "r2", self.NOW) is False
        assert alarm_base.clear_expired_legacy_pause(state_rules, "missing", self.NOW) is False


class TestPauseRuleNowAndResume:
    def test_pause_rule_now_creates_single_rule_pause(self) -> None:
        with patch("dashboard.services.alarm_base.alarm_pauses.create_pause", return_value={"pause_id": "p"}) as mock:
            alarm_base.pause_rule_now("alarm2", {"r1": "phw-to-mpi"}, "r1", 45, "Fix", "Matt")
        payload, known_rules = mock.call_args[0]
        assert payload["scope_type"] == "rule"
        assert payload["targets"] == [{"alarm_type": "alarm2", "rule_id": "r1"}]
        assert payload["end_mode"] == "duration"
        assert payload["duration_minutes"] == 45
        assert (payload["reason"], payload["requested_by"]) == ("Fix", "Matt")
        assert known_rules == {"alarm2": {"r1": "phw-to-mpi"}}

    def test_pause_rule_now_without_duration_is_indefinite(self) -> None:
        with patch("dashboard.services.alarm_base.alarm_pauses.create_pause") as mock:
            alarm_base.pause_rule_now("alarm1", {"r1": ""}, "r1", None, "Fix", "Matt")
        assert mock.call_args[0][0]["end_mode"] == "indefinite"

    def test_resume_rule_clears_legacy_and_cancels_record(self) -> None:
        with (
            patch("dashboard.services.alarm_base.unpause_rule") as mock_legacy,
            patch("dashboard.services.alarm_base.alarm_pauses.cancel_rule_pause") as mock_cancel,
        ):
            alarm_base.resume_rule("alarm3", {"r1": "phw-to-mpi"}, "r1", "Alarm 3")
        mock_legacy.assert_called_once_with("alarm3", "r1", "Alarm 3", "state")
        mock_cancel.assert_called_once_with("alarm3", "r1", "phw-to-mpi")

    def test_resume_rule_conflict_leaves_legacy_pause_untouched(self) -> None:
        conflict = alarm_base.alarm_pauses.PauseConflictError("Wider pause", "p9")
        with (
            patch("dashboard.services.alarm_base.unpause_rule") as mock_legacy,
            patch("dashboard.services.alarm_base.alarm_pauses.cancel_rule_pause", side_effect=conflict),
        ):
            with pytest.raises(alarm_base.alarm_pauses.PauseConflictError):
                alarm_base.resume_rule("alarm3", {"r1": "phw-to-mpi"}, "r1", "Alarm 3")
        mock_legacy.assert_not_called()


class TestPauseUnpauseRule:
    def test_unpause_rule_skips_write_when_no_legacy_pause(self) -> None:
        state = {"rules": {"rule-1": {"last_alarm_at": "z"}}}
        with (
            patch("dashboard.services.alarm_base.load_state", return_value=state),
            patch("dashboard.services.alarm_base.save_state") as mock_save,
        ):
            alarm_base.unpause_rule("alarm1", "rule-1", "Alarm 1")
        mock_save.assert_not_called()

    def test_unpause_rule_removes_pause_fields_but_keeps_other_state(self) -> None:
        existing_state = {"rules": {"rule-1": {"paused_until": "x", "pause_reason": "y", "last_alarm_at": "z"}}}
        with (
            patch("dashboard.services.alarm_base.load_state", return_value=existing_state),
            patch("dashboard.services.alarm_base.save_state") as mock_save,
        ):
            alarm_base.unpause_rule("alarm1", "rule-1", "Alarm 1")

        saved_state = mock_save.call_args[0][1]
        rule_state = saved_state["rules"]["rule-1"]
        assert "paused_until" not in rule_state
        assert "pause_reason" not in rule_state
        assert rule_state["last_alarm_at"] == "z"

    def test_unpause_rule_removes_rule_entry_when_it_becomes_empty(self) -> None:
        existing_state = {"rules": {"rule-1": {"paused_until": "x", "pause_reason": "y"}}}
        with (
            patch("dashboard.services.alarm_base.load_state", return_value=existing_state),
            patch("dashboard.services.alarm_base.save_state") as mock_save,
        ):
            alarm_base.unpause_rule("alarm1", "rule-1", "Alarm 1")

        saved_state = mock_save.call_args[0][1]
        assert "rule-1" not in saved_state["rules"]


class TestParseLogAnalyticsDatetime:
    def test_none_returns_none(self) -> None:
        assert alarm_base.parse_log_analytics_datetime(None) is None

    def test_naive_datetime_normalised_to_utc(self) -> None:
        naive = datetime(2026, 1, 1, 12, 0, 0)
        result = alarm_base.parse_log_analytics_datetime(naive)
        assert result is not None
        assert result.tzinfo == timezone.utc

    def test_iso_string_parsed_and_normalised(self) -> None:
        result = alarm_base.parse_log_analytics_datetime("2026-01-01T12:00:00")
        assert result is not None
        assert result.tzinfo == timezone.utc

    def test_invalid_value_returns_none(self) -> None:
        assert alarm_base.parse_log_analytics_datetime("not-a-date") is None


class TestFormatDuration:
    def test_under_one_minute(self) -> None:
        assert alarm_base.format_duration(0.5) == "< 1 minute"

    def test_singular_minute(self) -> None:
        assert alarm_base.format_duration(1) == "1 minute"

    def test_plural_minutes(self) -> None:
        assert alarm_base.format_duration(30) == "30 minutes"

    def test_hours(self) -> None:
        assert "hour" in alarm_base.format_duration(90)

    def test_days(self) -> None:
        assert "day" in alarm_base.format_duration(1440)
