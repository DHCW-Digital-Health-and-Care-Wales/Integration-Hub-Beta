"""Shared time-period utilities for the Integration Hub alarm services.

Provides a single, canonical implementation of the time-period classification
logic used by alarms that need to vary their thresholds across Day, Evening,
and Weekend windows.

Time windows (all UTC):
    Weekend : Friday 17:00 → Monday 08:00
    Day     : Monday–Friday 08:00–17:00
    Evening : all other times (Mon–Fri outside day hours)
"""

from __future__ import annotations

from datetime import datetime


def get_current_period(now: datetime) -> str:
    """Return the current time period: ``'day'``, ``'evening'``, or ``'weekend'``.

    Weekend : Friday 17:00 → Monday 08:00 (UTC)
    Day     : Monday–Friday 08:00–17:00 (UTC)
    Evening : Monday–Friday 17:00–08:00, excluding weekend window (UTC)

    Args:
        now: A timezone-aware (or naive UTC) datetime to evaluate.

    Returns:
        One of ``'day'``, ``'evening'``, or ``'weekend'``.
    """
    weekday = now.weekday()  # 0 = Monday … 4 = Friday, 5 = Sat, 6 = Sun
    time_mins = now.hour * 60 + now.minute
    DAY_START = 8 * 60  # 08:00
    DAY_END = 17 * 60  # 17:00

    # Weekend window: Fri 17:00 → Mon 08:00
    if weekday == 4 and time_mins >= DAY_END:  # Friday after 17:00
        return "weekend"
    if weekday in (5, 6):  # Saturday, Sunday
        return "weekend"
    if weekday == 0 and time_mins < DAY_START:  # Monday before 08:00
        return "weekend"

    # Day window: Mon–Fri 08:00–17:00
    if 0 <= weekday <= 4 and DAY_START <= time_mins < DAY_END:
        return "day"

    # Everything else is evening
    return "evening"


PERIOD_LABELS: dict[str, str] = {
    "day": "Day (Mon–Fri 08:00–17:00 UTC)",
    "evening": "Evening (Mon–Fri 17:00–08:00 UTC)",
    "weekend": "Weekend (Fri 17:00–Mon 08:00 UTC)",
}

PERIOD_SHORT_LABELS: dict[str, str] = {
    "day": "Day",
    "evening": "Evening",
    "weekend": "Weekend",
}
