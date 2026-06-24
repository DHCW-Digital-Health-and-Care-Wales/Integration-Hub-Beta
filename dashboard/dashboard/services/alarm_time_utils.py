"""Shared time-period utilities for the Integration Hub alarm services.

Provides a single, canonical implementation of the time-period classification
logic used by alarms that need to vary their thresholds across Day, Evening,
and Weekend windows.

Time windows (UK local time — Europe/London, handles BST/GMT automatically):
    Weekend : Friday 17:00 → Monday 09:00
    Day     : Monday–Friday 09:00–17:00
    Evening : all other times (Mon–Fri outside day hours)
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_LONDON_TZ = ZoneInfo("Europe/London")


def get_current_period(now: datetime) -> str:
    """Return the current time period: ``'day'``, ``'evening'``, or ``'weekend'``.

    Weekend : Friday 17:00 → Monday 09:00 (UK local time)
    Day     : Monday–Friday 09:00–17:00 (UK local time)
    Evening : Monday–Friday 17:00–09:00 (UK local time), excluding the Weekend window

    Args:
        now: A timezone-aware or naive (assumed UTC) datetime to evaluate.
             Classification is done in Europe/London time to handle BST/GMT correctly.

    Returns:
        One of ``'day'``, ``'evening'``, or ``'weekend'``.
    """
    # Normalise to UTC first, then convert to UK local time for classification.
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(_LONDON_TZ)
    weekday = now.weekday()  # 0 = Monday … 4 = Friday, 5 = Sat, 6 = Sun
    time_mins = now.hour * 60 + now.minute
    DAY_START = 9 * 60  # 09:00
    DAY_END = 17 * 60  # 17:00

    # Weekend window: Fri 17:00 → Mon 09:00
    if weekday == 4 and time_mins >= DAY_END:  # Friday after 17:00
        return "weekend"
    if weekday in (5, 6):  # Saturday, Sunday
        return "weekend"
    if weekday == 0 and time_mins < DAY_START:  # Monday before 09:00
        return "weekend"

    # Day window: Mon–Fri 09:00–17:00
    if 0 <= weekday <= 4 and DAY_START <= time_mins < DAY_END:
        return "day"

    # Everything else is evening
    return "evening"


PERIOD_LABELS: dict[str, str] = {
    "day": "Day (Mon–Fri 09:00–17:00 UK time)",
    "evening": "Evening (Mon–Fri 17:00–09:00 UK time; excluding Weekend)",
    "weekend": "Weekend (Fri 17:00–Mon 09:00 UK time)",
}

PERIOD_SHORT_LABELS: dict[str, str] = {
    "day": "Day",
    "evening": "Evening",
    "weekend": "Weekend",
}
