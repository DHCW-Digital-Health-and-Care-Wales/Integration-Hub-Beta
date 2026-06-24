"""Unit tests for alarm_time_utils.get_current_period().

All boundary cases for the three time periods (UK local time — Europe/London):
  Weekend : Fri 17:00 → Mon 09:00
  Day     : Mon–Fri 09:00–17:00
  Evening : everything else (weeknights)

UTC boundary notes (June — BST +01:00):
  Day start : 08:00 UTC = 09:00 BST
  Day end   : 16:00 UTC = 17:00 BST
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from datetime import timezone as tz

from dashboard.services.alarm_time_utils import get_current_period

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    """Return a UTC-aware datetime for the given components."""
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


# Anchor dates (all 2026):
#   Mon 22 Jun, Tue 23 Jun, Wed 24 Jun, Thu 25 Jun, Fri 26 Jun, Sat 27 Jun, Sun 28 Jun
MON = (2026, 6, 22)
TUE = (2026, 6, 23)
WED = (2026, 6, 24)
THU = (2026, 6, 25)
FRI = (2026, 6, 26)
SAT = (2026, 6, 27)
SUN = (2026, 6, 28)
# Next Monday
NEXT_MON = (2026, 6, 29)


# ---------------------------------------------------------------------------
# Weekend period
# ---------------------------------------------------------------------------


class TestWeekendPeriod:
    """Fri 17:00 through Mon 09:00 BST (exclusive) is always 'weekend'."""

    def test_friday_at_day_end_is_weekend(self) -> None:
        assert get_current_period(_utc(*FRI, 17, 0)) == "weekend"

    def test_friday_evening_is_weekend(self) -> None:
        assert get_current_period(_utc(*FRI, 20, 0)) == "weekend"

    def test_friday_midnight_is_weekend(self) -> None:
        assert get_current_period(_utc(*FRI, 23, 59)) == "weekend"

    def test_saturday_midnight_is_weekend(self) -> None:
        assert get_current_period(_utc(*SAT, 0, 0)) == "weekend"

    def test_saturday_midday_is_weekend(self) -> None:
        assert get_current_period(_utc(*SAT, 12, 0)) == "weekend"

    def test_sunday_midday_is_weekend(self) -> None:
        assert get_current_period(_utc(*SUN, 12, 0)) == "weekend"

    def test_monday_00_00_is_weekend(self) -> None:
        """Mon 00:00 is still inside the Fri 17:00 → Mon 09:00 BST window."""
        assert get_current_period(_utc(*NEXT_MON, 0, 0)) == "weekend"

    def test_monday_07_59_is_weekend(self) -> None:
        assert get_current_period(_utc(*NEXT_MON, 7, 59)) == "weekend"

    def test_friday_15_59_is_not_weekend(self) -> None:
        """One minute before 17:00 UK on Friday (15:59 UTC = 16:59 BST) is still Day."""
        assert get_current_period(_utc(*FRI, 15, 59)) == "day"

    def test_monday_08_00_is_not_weekend(self) -> None:
        """Mon 09:00 BST marks the start of Day — weekend ends here."""
        assert get_current_period(_utc(*NEXT_MON, 8, 0)) == "day"


# ---------------------------------------------------------------------------
# Day period
# ---------------------------------------------------------------------------


class TestDayPeriod:
    """Mon–Fri 09:00–17:00 UK (08:00–16:00 UTC in BST) is 'day'."""

    def test_monday_day_start(self) -> None:
        assert get_current_period(_utc(*MON, 8, 0)) == "day"

    def test_monday_midday(self) -> None:
        assert get_current_period(_utc(*MON, 12, 0)) == "day"

    def test_monday_last_minute(self) -> None:
        """15:59 UTC = 16:59 BST — one minute before 17:00 UK end of Day."""
        assert get_current_period(_utc(*MON, 15, 59)) == "day"

    def test_tuesday_midday(self) -> None:
        assert get_current_period(_utc(*TUE, 12, 0)) == "day"

    def test_wednesday_midday(self) -> None:
        assert get_current_period(_utc(*WED, 12, 0)) == "day"

    def test_thursday_midday(self) -> None:
        assert get_current_period(_utc(*THU, 12, 0)) == "day"

    def test_friday_day_start(self) -> None:
        assert get_current_period(_utc(*FRI, 8, 0)) == "day"

    def test_friday_midday(self) -> None:
        assert get_current_period(_utc(*FRI, 12, 0)) == "day"

    def test_friday_last_minute(self) -> None:
        """15:59 UTC = 16:59 BST — one minute before 17:00 UK end of Day."""
        assert get_current_period(_utc(*FRI, 15, 59)) == "day"


# ---------------------------------------------------------------------------
# Evening period
# ---------------------------------------------------------------------------


class TestEveningPeriod:
    """Weeknights (Mon–Thu 17:00 → next day 09:00 BST) are 'evening'."""

    def test_monday_17_00_is_evening(self) -> None:
        assert get_current_period(_utc(*MON, 17, 0)) == "evening"

    def test_monday_midnight_is_evening(self) -> None:
        assert get_current_period(_utc(*MON, 23, 59)) == "evening"

    def test_tuesday_00_00_is_evening(self) -> None:
        """Tue 00:00 is the overnight tail of Mon evening."""
        assert get_current_period(_utc(*TUE, 0, 0)) == "evening"

    def test_tuesday_07_59_is_evening(self) -> None:
        assert get_current_period(_utc(*TUE, 7, 59)) == "evening"

    def test_tuesday_17_00_is_evening(self) -> None:
        assert get_current_period(_utc(*TUE, 17, 0)) == "evening"

    def test_wednesday_17_00_is_evening(self) -> None:
        assert get_current_period(_utc(*WED, 17, 0)) == "evening"

    def test_thursday_17_00_is_evening(self) -> None:
        assert get_current_period(_utc(*THU, 17, 0)) == "evening"

    def test_friday_00_00_is_evening(self) -> None:
        """Fri 00:00–07:59 is the tail of Thu evening (not yet weekend)."""
        assert get_current_period(_utc(*FRI, 0, 0)) == "evening"

    def test_friday_07_59_is_evening(self) -> None:
        assert get_current_period(_utc(*FRI, 7, 59)) == "evening"


# ---------------------------------------------------------------------------
# UTC normalisation
# ---------------------------------------------------------------------------


class TestUTCNormalisation:
    """Timezone-aware non-UTC datetimes should be classified in UK local time."""

    def test_bst_aware_datetime_classified_in_uk_time(self) -> None:
        """A BST (+01:00) datetime of 16:00 BST = 16:00 UK time → 'day' (between 09:00–17:00 UK)."""
        bst = tz(timedelta(hours=1))
        # Tue 23 Jun 2026, 16:00 BST = 16:00 UK = day
        aware_bst = datetime(2026, 6, 23, 16, 0, tzinfo=bst)  # Tuesday
        assert get_current_period(aware_bst) == "day"

    def test_bst_aware_datetime_after_17_is_evening(self) -> None:
        """A BST (+01:00) datetime of 17:30 BST = 17:30 UK time → 'evening' (after 17:00 UK)."""
        bst = tz(timedelta(hours=1))
        aware_bst = datetime(2026, 6, 23, 17, 30, tzinfo=bst)  # Tuesday
        assert get_current_period(aware_bst) == "evening"

    def test_naive_datetime_treated_as_utc(self) -> None:
        """A naive datetime (no tzinfo) is treated as UTC."""
        naive_midday_mon = datetime(2026, 6, 22, 12, 0)  # Monday 12:00 UTC = 13:00 BST → day
        assert get_current_period(naive_midday_mon) == "day"
