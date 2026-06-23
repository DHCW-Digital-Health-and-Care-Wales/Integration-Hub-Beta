"""Unit tests for Alarm 2 service logic.

Tests cover:
  - _applicable_threshold()  : period selection and legacy config fallback
  - _build_row()             : per-period threshold display fields and legacy fallback
  - get_alarm2_config_page_data() : legacy 'threshold' fallback for all three periods
  - _window_label()          : minute-to-label formatting
  - generate_rule_id()       : unique ID generation
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from dashboard.services.alarm2 import (
    DEFAULT_DAY_THRESHOLD,
    DEFAULT_EVENING_THRESHOLD,
    DEFAULT_WEEKEND_THRESHOLD,
    _applicable_threshold,
    _build_row,
    _window_label,
    generate_rule_id,
    get_alarm2_config_page_data,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc(weekday_offset: int, hour: int) -> datetime:
    """Return a UTC datetime for a specific weekday in the anchor week (2026-06-22 = Mon).

    weekday_offset 0=Mon … 4=Fri, 5=Sat, 6=Sun
    """
    # Monday anchor
    base_day = 22 + weekday_offset
    return datetime(2026, 6, base_day, hour, 0, tzinfo=timezone.utc)


MON_DAY = _utc(0, 12)  # Monday 12:00 UTC → day
MON_EVE = _utc(0, 18)  # Monday 18:00 UTC → evening
FRI_EVE = _utc(4, 18)  # Friday 18:00 UTC → weekend
SAT_MID = _utc(5, 12)  # Saturday 12:00 UTC → weekend


# ---------------------------------------------------------------------------
# _applicable_threshold
# ---------------------------------------------------------------------------


class TestApplicableThreshold:
    """Threshold selection by current period, with legacy fallback."""

    def test_returns_day_threshold_during_day(self) -> None:
        cfg = {"day_threshold": 50, "evening_threshold": 20, "weekend_threshold": 5}
        assert _applicable_threshold(cfg, MON_DAY) == 50

    def test_returns_evening_threshold_during_evening(self) -> None:
        cfg = {"day_threshold": 50, "evening_threshold": 20, "weekend_threshold": 5}
        assert _applicable_threshold(cfg, MON_EVE) == 20

    def test_returns_weekend_threshold_during_weekend(self) -> None:
        cfg = {"day_threshold": 50, "evening_threshold": 20, "weekend_threshold": 5}
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
        cfg = {"threshold": 99, "day_threshold": 10}
        assert _applicable_threshold(cfg, MON_DAY) == 10

    def test_missing_config_returns_default(self) -> None:
        assert _applicable_threshold({}, MON_DAY) == DEFAULT_DAY_THRESHOLD
        assert _applicable_threshold({}, MON_EVE) == DEFAULT_EVENING_THRESHOLD
        assert _applicable_threshold({}, SAT_MID) == DEFAULT_WEEKEND_THRESHOLD

    def test_friday_17_is_weekend(self) -> None:
        """Friday 17:00 should be classified as weekend (priority rule)."""
        cfg = {"day_threshold": 50, "evening_threshold": 20, "weekend_threshold": 5}
        fri_17 = datetime(2026, 6, 26, 17, 0, tzinfo=timezone.utc)
        assert _applicable_threshold(cfg, fri_17) == 5


# ---------------------------------------------------------------------------
# _build_row
# ---------------------------------------------------------------------------


class TestBuildRow:
    """_build_row() assembles the status dict shown in the alarm 2 table."""

    _SEED = {"id": "phw-to-mpi-outgoing", "display_name": "PHW → MPI Outgoing", "workflow_id": "phw-to-mpi"}
    _CFG = {
        "display_name": "PHW → MPI Outgoing",
        "workflow_id": "phw-to-mpi",
        "day_threshold": 30,
        "evening_threshold": 15,
        "weekend_threshold": 5,
        "window_duration_minutes": 1440,
        "alerting_gap_minutes": 60,
    }

    def _row(self, now: datetime, **overrides) -> dict:
        cfg = {**self._CFG, **overrides}
        return _build_row(
            "phw-to-mpi-outgoing", self._SEED, cfg, total=100, status="healthy", cooldown_remaining=None, now=now
        )

    def test_period_threshold_matches_day(self) -> None:
        row = self._row(MON_DAY)
        assert row["current_period"] == "day"
        assert row["period_threshold"] == 30

    def test_period_threshold_matches_evening(self) -> None:
        row = self._row(MON_EVE)
        assert row["current_period"] == "evening"
        assert row["period_threshold"] == 15

    def test_period_threshold_matches_weekend(self) -> None:
        row = self._row(SAT_MID)
        assert row["current_period"] == "weekend"
        assert row["period_threshold"] == 5

    def test_all_three_threshold_fields_present(self) -> None:
        row = self._row(MON_DAY)
        assert row["day_threshold"] == 30
        assert row["evening_threshold"] == 15
        assert row["weekend_threshold"] == 5

    def test_legacy_threshold_fallback_in_display_fields(self) -> None:
        """Rows built from legacy config expose the legacy value for all three fields."""
        legacy_cfg = {
            "threshold": 77,
            "workflow_id": "phw-to-mpi",
            "window_duration_minutes": 1440,
            "alerting_gap_minutes": 60,
        }
        row = _build_row(
            "phw-to-mpi-outgoing",
            self._SEED,
            legacy_cfg,
            total=50,
            status="healthy",
            cooldown_remaining=None,
            now=MON_DAY,
        )
        assert row["day_threshold"] == 77
        assert row["evening_threshold"] == 77
        assert row["weekend_threshold"] == 77

    def test_messages_display_formats_with_commas(self) -> None:
        row = self._row(MON_DAY, **{})
        # total=100 passed above
        assert row["messages_display"] == "100"

    def test_messages_display_dash_when_none(self) -> None:
        row = _build_row(
            "phw-to-mpi-outgoing",
            self._SEED,
            self._CFG,
            total=None,
            status="unknown",
            cooldown_remaining=None,
            now=MON_DAY,
        )
        assert row["messages_display"] == "—"

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
                    "day_threshold": 10,
                    "evening_threshold": 5,
                    "weekend_threshold": 2,
                    "window_duration_minutes": 1440,
                    "alerting_gap_minutes": 60,
                }
            }
        }
        with patch("dashboard.services.alarm2.load_alarm2_config", return_value=fake_cfg):
            data = get_alarm2_config_page_data()

        rule = next(r for r in data if r["id"] == "phw-to-mpi-outgoing")
        assert rule["day_threshold"] == 10
        assert rule["evening_threshold"] == 5
        assert rule["weekend_threshold"] == 2

    def test_legacy_config_fans_out_threshold_to_all_periods(self) -> None:
        fake_cfg = {
            "rules": {
                "phw-to-mpi-outgoing": {
                    "alarm_enabled": True,
                    "workflow_id": "phw-to-mpi",
                    "threshold": 42,  # Legacy single value
                    "window_duration_minutes": 1440,
                    "alerting_gap_minutes": 60,
                }
            }
        }
        with patch("dashboard.services.alarm2.load_alarm2_config", return_value=fake_cfg):
            data = get_alarm2_config_page_data()

        rule = next(r for r in data if r["id"] == "phw-to-mpi-outgoing")
        assert rule["day_threshold"] == 42
        assert rule["evening_threshold"] == 42
        assert rule["weekend_threshold"] == 42

    def test_missing_config_returns_defaults(self) -> None:
        with patch("dashboard.services.alarm2.load_alarm2_config", return_value={"rules": {}}):
            data = get_alarm2_config_page_data()

        rule = next(r for r in data if r["id"] == "phw-to-mpi-outgoing")
        assert rule["day_threshold"] == DEFAULT_DAY_THRESHOLD
        assert rule["evening_threshold"] == DEFAULT_EVENING_THRESHOLD
        assert rule["weekend_threshold"] == DEFAULT_WEEKEND_THRESHOLD
        assert rule["alarm_enabled"] is False


# ---------------------------------------------------------------------------
# _window_label
# ---------------------------------------------------------------------------


class TestWindowLabel:
    def test_minutes_below_hour(self) -> None:
        assert _window_label(30) == "30 min"

    def test_exactly_one_hour(self) -> None:
        assert _window_label(60) == "1 hr"

    def test_multiple_hours(self) -> None:
        assert _window_label(120) == "2 hrs"

    def test_exactly_one_day(self) -> None:
        assert _window_label(1440) == "1 day"

    def test_multiple_days(self) -> None:
        assert _window_label(2880) == "2 days"


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
