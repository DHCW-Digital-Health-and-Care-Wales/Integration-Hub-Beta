"""Jinja2 template filters shared across dashboard templates.

Extracted from ``dashboard.app`` as the final step of the app.py route/filter
split. These are plain functions registered onto the app by ``register(app)``
so ``app.py`` doesn't need to import Jinja/Flask filter decorators directly.
"""

from __future__ import annotations

from flask import Flask


def format_bytes(size: int | float) -> str:
    """Jinja2 filter: convert a byte count to a human-readable string (e.g. ``1.4 MB``)."""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size = size / 1024
    return f"{size:.1f} TB"


def health_badge(health: str) -> str:
    """Jinja2 filter: map a health string to a Bootstrap colour token (e.g. ``"healthy"`` → ``"success"``)."""
    colours = {
        "healthy": "success",
        "warning": "warning",
        "critical": "danger",
        "unknown": "secondary",
    }
    return colours.get(health, "secondary")


def register(app: Flask) -> None:
    """Register every template filter onto ``app`` under its original filter name."""
    app.add_template_filter(format_bytes, name="format_bytes")
    app.add_template_filter(health_badge, name="health_badge")
