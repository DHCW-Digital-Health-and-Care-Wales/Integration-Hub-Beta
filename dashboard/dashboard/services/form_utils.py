"""
Shared helpers for parsing Flask ``request.form`` data.

Extracted from the near-identical ``_int`` closures previously duplicated in
``alarm_config_page``, ``alarm2_config_page`` and ``alarm3_config_page`` in
``dashboard/app.py``.
"""

from __future__ import annotations

from werkzeug.datastructures import ImmutableMultiDict


def parse_int_form_field(
    form: ImmutableMultiDict,
    field: str,
    default: int,
    minimum: int = 1,
) -> int:
    """Parse an integer field from a submitted form, clamped to a minimum.

    Falls back to ``default`` if the field is missing or not a valid integer.
    Mirrors the previous per-route ``_int`` closures: alarm1's implicit
    ``max(1, ...)`` behaviour is preserved via the ``minimum=1`` default.
    """
    try:
        return max(minimum, int(form.get(field, default)))
    except (ValueError, TypeError):
        return default
