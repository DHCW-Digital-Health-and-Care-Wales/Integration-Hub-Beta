"""TTL unit conversion for the GUI; the stored form is always whole seconds."""

from __future__ import annotations

from lookup_service.errors import InvalidSettingsError
from lookup_service.models import MAX_TTL_SECONDS

# Largest first, so split_ttl picks the most readable exact unit.
TTL_UNITS: dict[str, int] = {"days": 86400, "hours": 3600, "minutes": 60, "seconds": 1}


def ttl_to_seconds(value: int, unit: str, table: str | None = None) -> int:
    if unit not in TTL_UNITS:
        raise InvalidSettingsError("TTL unit must be one of " + ", ".join(reversed(TTL_UNITS)), table)
    seconds = value * TTL_UNITS[unit]
    if value < 1 or seconds > MAX_TTL_SECONDS:
        raise InvalidSettingsError(
            f"TTL must be between 1 second and {MAX_TTL_SECONDS // TTL_UNITS['days']} days", table
        )
    return seconds


def split_ttl(seconds: int) -> tuple[int, str]:
    """The largest unit that divides `seconds` exactly, e.g. 7200 -> (2, 'hours')."""
    for unit, size in TTL_UNITS.items():
        if seconds % size == 0:
            return seconds // size, unit
    return seconds, "seconds"  # pragma: no cover - 'seconds' always divides


def format_ttl(seconds: int) -> str:
    value, unit = split_ttl(seconds)
    return f"{value} {unit[:-1] if value == 1 else unit}"
