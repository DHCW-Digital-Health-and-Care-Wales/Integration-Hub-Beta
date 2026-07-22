"""Unit tests for Alarm 2 service logic.

Tests cover:
  - _applicable_threshold()      : period selection and legacy config fallback
  - _build_row()                 : per-period threshold display fields and inactivity data
  - _format_duration()           : duration formatting helper
  - get_alarm2_config_page_data(): legacy 'threshold' fallback for all three periods
  - generate_rule_id()           : unique ID generation
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

from dashboard.services.alarm2 import (
    DEFAULT_DAY_THRESHOLD,
    DEFAULT_EVENING_THRESHOLD,
    DEFAULT_WEEKEND_THRESHOLD,
    _applicable_threshold,
    _build_row,
    _format_duration,
    _send_alarm2_email,
    generate_rule_id,
    get_alarm2_config_page_data,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc(weekday_offset: int, hour: int) -> datetime:
    """Return a UTC datetime for a specific weekday in the anchor week (2026-06-22 = Mon).

    weekday_offset 0=Mon … 4=Fri, 5=Sat, 6=Sun.
    June 2026 is BST (+01:00), so UTC 08:00 = 09:00 UK (day start),
    UTC 16:00 = 17:00 UK (day end).
    """
    base_day = 22 + weekday_offset
    return datetime(2026, 6, base_day, hour, 0, tzinfo=timezone.utc)


MON_DAY = _utc(0, 12)  # Monday 12:00 UTC = 13:00 BST → day
MON_EVE = _utc(0, 18)  # Monday 18:00 UTC = 19:00 BST → evening
FRI_EVE = _utc(4, 18)  # Friday 18:00 UTC = 19:00 BST → weekend
SAT_MID = _utc(5, 12)  # Saturday 12:00 UTC = 13:00 BST → weekend

# A known last-message time 30 minutes before MON_DAY
LAST_MSG_30_AGO = datetime(2026, 6, 22, 11, 30, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# _applicable_threshold
# ---------------------------------------------------------------------------


class TestApplicableThreshold:
    """Threshold selection by current period, with legacy config fallback."""

    def test_returns_day_threshold_during_day(self) -> None:
        cfg = {"day_threshold_minutes": 50, "evening_threshold_minutes": 20, "weekend_threshold_minutes": 5}
        assert _applicable_threshold(cfg, MON_DAY) == 50

    def test_returns_evening_threshold_during_evening(self) -> None:
        cfg = {"day_threshold_minutes": 50, "evening_threshold_minutes": 20, "weekend_threshold_minutes": 5}
        assert _applicable_threshold(cfg, MON_EVE) == 20

    def test_returns_weekend_threshold_during_weekend(self) -> None:
        cfg = {"day_threshold_minutes": 50, "evening_threshold_minutes": 20, "weekend_threshold_minutes": 5}
        assert _applicable_threshold(cfg, SAT_MID) == 5

    def test_legacy_threshold_used_as_day_fallback(self) -> None:
        """Old config with only 'threshold' key → all periods fall back to that value."""
        cfg = {"threshold": 99}
        assert _applicable_threshold(cfg, MON_DAY) == 99

    def test_legacy_threshold_used_as_evening_fallback(self) -> None:
        cfg = {"threshold": 99}
        assert _applicable_threshold(cfg, MON_EVE) == 99

    def test_legacy_threshold_used_as_weekend_fallback(self) -> None:
        cfg = {"threshold": 99}
        assert _applicable_threshold(cfg, SAT_MID) == 99

    def test_per_period_takes_precedence_over_legacy(self) -> None:
        """Explicit per-period key wins over legacy 'threshold'."""
        cfg = {"threshold": 99, "day_threshold_minutes": 10}
        assert _applicable_threshold(cfg, MON_DAY) == 10

    def test_missing_config_returns_default(self) -> None:
        assert _applicable_threshold({}, MON_DAY) == DEFAULT_DAY_THRESHOLD
        assert _applicable_threshold({}, MON_EVE) == DEFAULT_EVENING_THRESHOLD
        assert _applicable_threshold({}, SAT_MID) == DEFAULT_WEEKEND_THRESHOLD

    def test_friday_17_utc_is_weekend(self) -> None:
        """Friday 17:00 UTC = 18:00 BST — well into weekend window."""
        cfg = {"day_threshold_minutes": 50, "evening_threshold_minutes": 20, "weekend_threshold_minutes": 5}
        fri_17 = datetime(2026, 6, 26, 17, 0, tzinfo=timezone.utc)
        assert _applicable_threshold(cfg, fri_17) == 5


# ---------------------------------------------------------------------------
# _build_row
# ---------------------------------------------------------------------------


class TestBuildRow:
    """_build_row() assembles the status dict shown in the Alarm 2 table."""

    _SEED = {"id": "phw-to-mpi-outgoing", "display_name": "PHW → MPI Outgoing", "workflow_id": "phw-to-mpi"}
    _CFG = {
        "display_name": "PHW → MPI Outgoing",
        "workflow_id": "phw-to-mpi",
        "day_threshold_minutes": 30,
        "evening_threshold_minutes": 15,
        "weekend_threshold_minutes": 5,
        "alerting_gap_minutes": 60,
    }

    def _row(
        self,
        now: datetime,
        last_msg: datetime | None = LAST_MSG_30_AGO,
        minutes_since: float | None = 30.0,
        status: str = "healthy",
        **cfg_overrides: Any,
    ) -> dict:
        cfg = {**self._CFG, **cfg_overrides}
        return _build_row(
            "phw-to-mpi-outgoing",
            self._SEED,
            cfg,
            last_msg=last_msg,
            status=status,
            minutes_since=minutes_since,
            cooldown_remaining=None,
            now=now,
        )

    def test_period_threshold_matches_day(self) -> None:
        row = self._row(MON_DAY)
        assert row["current_period"] == "day"
        assert row["period_threshold_minutes"] == 30

    def test_period_threshold_matches_evening(self) -> None:
        row = self._row(MON_EVE)
        assert row["current_period"] == "evening"
        assert row["period_threshold_minutes"] == 15

    def test_period_threshold_matches_weekend(self) -> None:
        row = self._row(SAT_MID)
        assert row["current_period"] == "weekend"
        assert row["period_threshold_minutes"] == 5

    def test_all_three_threshold_fields_present(self) -> None:
        row = self._row(MON_DAY)
        assert row["day_threshold_minutes"] == 30
        assert row["evening_threshold_minutes"] == 15
        assert row["weekend_threshold_minutes"] == 5

    def test_legacy_threshold_fallback_in_display_fields(self) -> None:
        """Rows built from legacy config expose the legacy 'threshold' value for all three
        display fields, so the table shows a meaningful number rather than the default."""
        legacy_cfg = {
            "threshold": 77,
            "workflow_id": "phw-to-mpi",
            "alerting_gap_minutes": 60,
        }
        row = _build_row(
            "phw-to-mpi-outgoing",
            self._SEED,
            legacy_cfg,
            last_msg=LAST_MSG_30_AGO,
            status="healthy",
            minutes_since=30.0,
            cooldown_remaining=None,
            now=MON_DAY,
        )
        assert row["day_threshold_minutes"] == 77
        assert row["evening_threshold_minutes"] == 77
        assert row["weekend_threshold_minutes"] == 77

    def test_last_message_display_populated(self) -> None:
        row = self._row(MON_DAY)
        assert "22 Jun 2026" in row["last_message_display"]
        assert "UTC" in row["last_message_display"]

    def test_last_message_display_unknown_when_none(self) -> None:
        row = self._row(MON_DAY, last_msg=None, minutes_since=None, status="unknown")
        assert row["last_message_display"] == "Never / unknown"

    def test_duration_label_populated(self) -> None:
        row = self._row(MON_DAY, minutes_since=30.0)
        assert row["duration_label"] == "30 minutes"

    def test_duration_label_no_data_when_none(self) -> None:
        row = self._row(MON_DAY, last_msg=None, minutes_since=None, status="unknown")
        assert row["duration_label"] == "No data"

    def test_status_preserved(self) -> None:
        row = self._row(MON_DAY)
        assert row["status"] == "healthy"

    def test_period_short_label_day(self) -> None:
        row = self._row(MON_DAY)
        assert row["period_short_label"] == "Day"

    def test_period_short_label_evening(self) -> None:
        row = self._row(MON_EVE)
        assert row["period_short_label"] == "Evening"

    def test_period_short_label_weekend(self) -> None:
        row = self._row(SAT_MID)
        assert row["period_short_label"] == "Weekend"


# ---------------------------------------------------------------------------
# _format_duration
# ---------------------------------------------------------------------------


class TestFormatDuration:
    def test_below_one_minute(self) -> None:
        assert _format_duration(0.5) == "< 1 minute"

    def test_one_minute(self) -> None:
        assert _format_duration(1) == "1 minute"

    def test_multiple_minutes(self) -> None:
        assert _format_duration(30) == "30 minutes"

    def test_hours(self) -> None:
        assert "hour" in _format_duration(90)

    def test_days(self) -> None:
        assert "day" in _format_duration(1440)


# ---------------------------------------------------------------------------
# get_alarm2_config_page_data — legacy fallback
# ---------------------------------------------------------------------------


class TestGetAlarm2ConfigPageData:
    """Config page data builder correctly handles both new-style and legacy configs."""

    def test_new_style_config_returns_per_period_values(self) -> None:
        fake_cfg = {
            "rules": {
                "phw-to-mpi-outgoing": {
                    "alarm_enabled": True,
                    "workflow_id": "phw-to-mpi",
                    "day_threshold_minutes": 10,
                    "evening_threshold_minutes": 5,
                    "weekend_threshold_minutes": 2,
                    "alerting_gap_minutes": 60,
                }
            }
        }
        with patch("dashboard.services.alarm2.load_alarm2_config", return_value=fake_cfg):
            data = get_alarm2_config_page_data()

        rule = next(r for r in data if r["id"] == "phw-to-mpi-outgoing")
        assert rule["day_threshold_minutes"] == 10
        assert rule["evening_threshold_minutes"] == 5
        assert rule["weekend_threshold_minutes"] == 2

    def test_legacy_config_fans_out_threshold_to_all_periods(self) -> None:
        fake_cfg = {
            "rules": {
                "phw-to-mpi-outgoing": {
                    "alarm_enabled": True,
                    "workflow_id": "phw-to-mpi",
                    "threshold": 42,  # Legacy single value
                    "alerting_gap_minutes": 60,
                }
            }
        }
        with patch("dashboard.services.alarm2.load_alarm2_config", return_value=fake_cfg):
            data = get_alarm2_config_page_data()

        rule = next(r for r in data if r["id"] == "phw-to-mpi-outgoing")
        assert rule["day_threshold_minutes"] == 42
        assert rule["evening_threshold_minutes"] == 42
        assert rule["weekend_threshold_minutes"] == 42

    def test_missing_config_returns_defaults(self) -> None:
        with patch("dashboard.services.alarm2.load_alarm2_config", return_value={"rules": {}}):
            data = get_alarm2_config_page_data()

        rule = next(r for r in data if r["id"] == "phw-to-mpi-outgoing")
        assert rule["day_threshold_minutes"] == DEFAULT_DAY_THRESHOLD
        assert rule["evening_threshold_minutes"] == DEFAULT_EVENING_THRESHOLD
        assert rule["weekend_threshold_minutes"] == DEFAULT_WEEKEND_THRESHOLD
        assert rule["alarm_enabled"] is False


# ---------------------------------------------------------------------------
# generate_rule_id
# ---------------------------------------------------------------------------


class TestGenerateRuleId:
    def test_basic_id_generation(self) -> None:
        assert generate_rule_id("phw-to-mpi", set()) == "phw-to-mpi-outgoing"

    def test_avoids_duplicate_ids(self) -> None:
        existing = {"phw-to-mpi-outgoing"}
        assert generate_rule_id("phw-to-mpi", existing) == "phw-to-mpi-outgoing-2"

    def test_increments_further_on_collision(self) -> None:
        existing = {"phw-to-mpi-outgoing", "phw-to-mpi-outgoing-2"}
        assert generate_rule_id("phw-to-mpi", existing) == "phw-to-mpi-outgoing-3"

    def test_workflow_id_normalised_to_kebab(self) -> None:
        rid = generate_rule_id("PHW to MPI", set())
        assert rid == "phw-to-mpi-outgoing"


class TestSendAlarm2Email:
    """_send_alarm2_email() must not log an ERROR when send_alert_email() returns False
    for the intentional/expected reason that ALERT_EMAIL_ENABLED is globally off — that
    is not a failure, and send_alert_email() logs nothing itself in that case."""

    def test_no_error_log_when_alert_email_globally_disabled(self, caplog: Any) -> None:
        with (
            patch("dashboard.services.alarm2.send_alert_email", return_value=False),
            patch("dashboard.services.alarm2.config.ALERT_EMAIL_ENABLED", False),
            caplog.at_level("WARNING", logger="dashboard.services.alarm2"),
        ):
            _send_alarm2_email(
                "rid", "phw-to-mpi", "PHW to MPI", 30.0, 15, LAST_MSG_30_AGO, MON_DAY, email_alerts_enabled=True
            )
        assert not any(r.levelname == "ERROR" for r in caplog.records)
        assert not any("Failed to send alarm 2 email" in r.message for r in caplog.records)

    def test_warning_log_when_send_fails_with_email_enabled(self, caplog: Any) -> None:
        with (
            patch("dashboard.services.alarm2.send_alert_email", return_value=False),
            patch("dashboard.services.alarm2.config.ALERT_EMAIL_ENABLED", True),
            caplog.at_level("WARNING", logger="dashboard.services.alarm2"),
        ):
            _send_alarm2_email(
                "rid", "phw-to-mpi", "PHW to MPI", 30.0, 15, LAST_MSG_30_AGO, MON_DAY, email_alerts_enabled=True
            )
        assert any(
            r.levelname == "WARNING" and "Failed to send alarm 2 email" in r.message for r in caplog.records
        )
