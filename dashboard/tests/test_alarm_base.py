"""
Unit tests for dashboard.services.alarm_base — the shared Cosmos DB config/
state persistence and pause/unpause helpers used by alarm1.py, alarm2.py,
and alarm3.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

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
        mock_upsert.assert_called_once_with("alarm3", "config", {"rules": {}})


class TestLoadSaveState:
    def test_load_state_returns_empty_rules_when_no_document_stored(self) -> None:
        with patch("dashboard.services.alarm_base.cosmos_store.get_document", return_value=None):
            assert alarm_base.load_state("alarm1") == {"rules": {}}

    def test_save_state_upserts_with_partition_and_doc_id(self) -> None:
        with patch("dashboard.services.alarm_base.cosmos_store.upsert_document") as mock_upsert:
            alarm_base.save_state("alarm2", {"rules": {"r1": {}}}, "state")
        mock_upsert.assert_called_once_with("alarm2", "state", {"rules": {"r1": {}}})


class TestPauseUnpauseRule:
    def test_pause_rule_writes_paused_until_and_reason(self) -> None:
        with (
            patch("dashboard.services.alarm_base.load_state", return_value={"rules": {}}) as mock_load,
            patch("dashboard.services.alarm_base.save_state") as mock_save,
        ):
            alarm_base.pause_rule("alarm1", "rule-1", 30, "maintenance", "Alarm 1")

        mock_load.assert_called_once_with("alarm1", "state")
        saved_state = mock_save.call_args[0][1]
        rule_state = saved_state["rules"]["rule-1"]
        assert rule_state["pause_reason"] == "maintenance"
        paused_until = datetime.fromisoformat(rule_state["paused_until"])
        assert paused_until > datetime.now(timezone.utc)
        assert paused_until < datetime.now(timezone.utc) + timedelta(minutes=31)

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
