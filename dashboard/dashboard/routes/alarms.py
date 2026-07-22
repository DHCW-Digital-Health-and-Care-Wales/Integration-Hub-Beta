"""Alarm overview/status pages and pause/unpause actions for Alarms 1-3.

Extracted from ``dashboard.app`` as part of the route-module split. These are
plain view functions (no Flask ``Blueprint`` — see ``dashboard.routes``
module docstring for why), registered onto the app by ``register(app)`` with
explicit endpoint names matching their original flat names so existing
``url_for(...)`` calls and any programmatic references keep working
unchanged.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

from flask import Flask, Response, current_app, jsonify, render_template, request

import dashboard.config as config
from dashboard.services import cache
from dashboard.services.alarm1 import (
    get_alarm_status,
    load_alarm_config,
    pause_alarm_rule,
    unpause_alarm_rule,
)
from dashboard.services.alarm2 import (
    get_alarm2_status,
    load_alarm2_config,
    pause_alarm2_rule,
    unpause_alarm2_rule,
)
from dashboard.services.alarm3 import (
    get_alarm3_status,
    load_alarm3_config,
    pause_alarm3_rule,
    unpause_alarm3_rule,
)
from dashboard.services.status_builder import LONDON_TZ

# Sort order used to bubble paused/critical rows to the top of alarm tables.
_PAUSE_ORDER = {"paused": 0, "critical": 1, "suppressed": 2, "unknown": 3, "healthy": 4}


def alarms_overview_page() -> str:
    """Render the Alarms overview page showing all three alarm-type summaries."""
    if request.args.get("refresh") == "1":
        with cache.cache_lock:
            cache.cache_data["alarms"]["ts"] = 0.0
            cache.cache_data["alarm2"]["ts"] = 0.0
            cache.cache_data["alarm3"]["ts"] = 0.0

    # Fetch all three alarm statuses concurrently — cold fetches run in
    # parallel threads instead of blocking sequentially.
    alarm1_rows, alarm2_rows, alarm3_rows = cache.multi_cached_nowait(
        [
            ("alarms", get_alarm_status, config.API_CACHE_TTL),
            ("alarm2", get_alarm2_status, config.API_CACHE_TTL),
            ("alarm3", get_alarm3_status, config.API_CACHE_TTL),
        ]
    )

    cfg1 = load_alarm_config()
    any_alarm1 = any(s.get("alarm_enabled", False) for s in cfg1.get("rules", {}).values())
    cfg2 = load_alarm2_config()
    any_alarm2 = any(r.get("alarm_enabled", False) for r in cfg2.get("rules", {}).values())
    cfg3 = load_alarm3_config()
    any_alarm3 = any(r.get("alarm_enabled", False) for r in cfg3.get("rules", {}).values())
    return render_template(
        "alarms_overview.html",
        alarm1_rows=alarm1_rows,
        no_alarm1_configured=not any_alarm1,
        alarm2_rows=alarm2_rows,
        no_alarm2_configured=not any_alarm2,
        alarm3_rows=alarm3_rows,
        no_alarm3_configured=not any_alarm3,
        config_ok=bool(config.AZURE_LOG_ANALYTICS_WORKSPACE_ID),
        refreshed_at=datetime.now(LONDON_TZ).strftime("%d %b %Y  %H:%M:%S %Z"),
        refresh_interval=int(config.API_CACHE_TTL),
    )


def alarm_page() -> str:
    """Render the Inactivity Alarm status page (Alarm 1)."""
    alarm_rows = cache.cached_nowait(
        "alarms",
        get_alarm_status,
        ttl=config.API_CACHE_TTL,
    )
    # Determine whether any alarms have been configured at all
    cfg = load_alarm_config()
    any_configured = any(s.get("alarm_enabled", False) for s in cfg.get("rules", {}).values())
    return render_template(
        "alarm.html",
        alarm_rows=alarm_rows,
        no_alarms_configured=not any_configured,
        config_ok=bool(config.AZURE_LOG_ANALYTICS_WORKSPACE_ID),
        refreshed_at=datetime.now(LONDON_TZ).strftime("%d %b %Y  %H:%M:%S %Z"),
        data_is_stale=cache.is_cache_stale("alarms"),
    )


def alarm1_pause(rule_id: str) -> tuple[Response, int] | Response:
    """Pause an Alarm 1 rule for a given duration with an optional reason.

    Expects a JSON body: ``{"duration_minutes": int, "reason": str}``.
    Optimistically updates the in-memory cache so the page reload is instant
    rather than waiting for a fresh Azure Log Analytics query.
    """
    data = request.get_json(silent=True) or {}
    try:
        duration = int(data.get("duration_minutes", 60))
        if duration < 1:
            raise ValueError("duration_minutes must be >= 1")
    except (TypeError, ValueError) as exc:
        current_app.logger.warning("Invalid pause request payload: %s", exc)
        return jsonify({"ok": False, "error": "Invalid duration_minutes value."}), 400

    reason = str(data.get("reason", "")).strip()
    pause_alarm_rule(rule_id, duration, reason)

    # Optimistically patch the cached row so the page reload is instant.
    now = datetime.now(LONDON_TZ)
    paused_until_dt = now + timedelta(minutes=duration)
    with cache.cache_lock:
        cached_rows = cache.cache_data.get("alarms", {}).get("data")
        if isinstance(cached_rows, list):
            for row in cached_rows:
                if row.get("id") == rule_id:
                    row["status"] = "paused"
                    row["pause_remaining"] = float(duration)
                    row["pause_reason"] = reason
                    row["paused_until"] = paused_until_dt.strftime("%d %b %Y  %H:%M %Z")
                    break
            cached_rows.sort(key=lambda r: _PAUSE_ORDER.get(r.get("status", ""), 9))
            cache.cache_data["alarms"]["data"] = cached_rows
            cache.cache_data["alarms"]["ts"] = time.monotonic()  # mark as fresh
    return jsonify({"ok": True})


def alarm1_unpause(rule_id: str) -> Response:
    """Remove a manual pause from an Alarm 1 rule, restoring normal evaluation.

    Optimistically sets the row to 'unknown' in the cache so the reload is
    instant, then marks the cache as stale so a background refresh re-evaluates
    the true alarm status shortly afterwards.
    """
    unpause_alarm_rule(rule_id)

    # Optimistically patch the cached row: show 'unknown' instantly,
    # then let the stale cache trigger a background re-evaluation.
    with cache.cache_lock:
        cached_rows = cache.cache_data.get("alarms", {}).get("data")
        if isinstance(cached_rows, list):
            for row in cached_rows:
                if row.get("id") == rule_id:
                    row["status"] = "unknown"
                    row.pop("pause_remaining", None)
                    row.pop("pause_reason", None)
                    row.pop("paused_until", None)
                    break
            cached_rows.sort(key=lambda r: _PAUSE_ORDER.get(r.get("status", ""), 9))
            cache.cache_data["alarms"]["data"] = cached_rows
        # Mark stale — background refresh will resolve the true status shortly.
        if "alarms" in cache.cache_data:
            cache.cache_data["alarms"]["ts"] = 0.0
    return jsonify({"ok": True})


def alarm2_pause(rule_id: str) -> tuple[Response, int] | Response:
    """Pause an Alarm 2 rule for a given duration with an optional reason."""
    data = request.get_json(silent=True) or {}
    try:
        duration = int(data.get("duration_minutes", 60))
        if duration < 1:
            raise ValueError("duration_minutes must be >= 1")
    except (TypeError, ValueError):
        logging.getLogger(__name__).warning(
            "Invalid pause request payload for alarm2 rule_id=%s",
            rule_id,
            exc_info=True,
        )
        return jsonify({"ok": False, "error": "Invalid duration_minutes value."}), 400

    reason = str(data.get("reason", "")).strip()
    pause_alarm2_rule(rule_id, duration, reason)

    now = datetime.now(LONDON_TZ)
    paused_until_dt = now + timedelta(minutes=duration)
    with cache.cache_lock:
        cached_rows = cache.cache_data.get("alarm2", {}).get("data")
        if isinstance(cached_rows, list):
            for row in cached_rows:
                if row.get("id") == rule_id:
                    row["status"] = "paused"
                    row["pause_remaining"] = float(duration)
                    row["pause_reason"] = reason
                    row["paused_until"] = paused_until_dt.strftime("%d %b %Y  %H:%M %Z")
                    break
            cached_rows.sort(key=lambda r: _PAUSE_ORDER.get(r.get("status", ""), 9))
            cache.cache_data["alarm2"]["data"] = cached_rows
            cache.cache_data["alarm2"]["ts"] = time.monotonic()
    return jsonify({"ok": True})


def alarm2_unpause(rule_id: str) -> Response:
    """Remove a manual pause from an Alarm 2 rule, restoring normal evaluation."""
    unpause_alarm2_rule(rule_id)

    with cache.cache_lock:
        cached_rows = cache.cache_data.get("alarm2", {}).get("data")
        if isinstance(cached_rows, list):
            for row in cached_rows:
                if row.get("id") == rule_id:
                    row["status"] = "unknown"
                    row.pop("pause_remaining", None)
                    row.pop("pause_reason", None)
                    row.pop("paused_until", None)
                    break
            cached_rows.sort(key=lambda r: _PAUSE_ORDER.get(r.get("status", ""), 9))
            cache.cache_data["alarm2"]["data"] = cached_rows
        if "alarm2" in cache.cache_data:
            cache.cache_data["alarm2"]["ts"] = 0.0
    return jsonify({"ok": True})


def alarm3_pause(rule_id: str) -> tuple[Response, int] | Response:
    """Pause an Alarm 3 rule for a given duration with an optional reason."""
    data = request.get_json(silent=True) or {}
    try:
        duration = int(data.get("duration_minutes", 60))
        if duration < 1:
            raise ValueError("duration_minutes must be >= 1")
    except (TypeError, ValueError):
        logging.warning("Invalid alarm3 pause payload", exc_info=True)
        return jsonify({"ok": False, "error": "Invalid request payload."}), 400

    reason = str(data.get("reason", "")).strip()
    pause_alarm3_rule(rule_id, duration, reason)

    now = datetime.now(LONDON_TZ)
    paused_until_dt = now + timedelta(minutes=duration)
    with cache.cache_lock:
        cached_rows = cache.cache_data.get("alarm3", {}).get("data")
        if isinstance(cached_rows, list):
            for row in cached_rows:
                if row.get("id") == rule_id:
                    row["status"] = "paused"
                    row["pause_remaining"] = float(duration)
                    row["pause_reason"] = reason
                    row["paused_until"] = paused_until_dt.strftime("%d %b %Y  %H:%M %Z")
                    break
            cached_rows.sort(key=lambda r: _PAUSE_ORDER.get(r.get("status", ""), 9))
            cache.cache_data["alarm3"]["data"] = cached_rows
            cache.cache_data["alarm3"]["ts"] = time.monotonic()
    return jsonify({"ok": True})


def alarm3_unpause(rule_id: str) -> Response:
    """Remove a manual pause from an Alarm 3 rule, restoring normal evaluation."""
    unpause_alarm3_rule(rule_id)

    with cache.cache_lock:
        cached_rows = cache.cache_data.get("alarm3", {}).get("data")
        if isinstance(cached_rows, list):
            for row in cached_rows:
                if row.get("id") == rule_id:
                    row["status"] = "unknown"
                    row.pop("pause_remaining", None)
                    row.pop("pause_reason", None)
                    row.pop("paused_until", None)
                    break
            cached_rows.sort(key=lambda r: _PAUSE_ORDER.get(r.get("status", ""), 9))
            cache.cache_data["alarm3"]["data"] = cached_rows
        if "alarm3" in cache.cache_data:
            cache.cache_data["alarm3"]["ts"] = 0.0
    return jsonify({"ok": True})


def alarm2_page() -> str:
    """Render the Outgoing Messages Alarm status page (Alarm 2)."""
    alarm2_rows = cache.cached_nowait(
        "alarm2",
        get_alarm2_status,
        ttl=config.API_CACHE_TTL,
    )
    cfg = load_alarm2_config()
    any_configured = any(r.get("alarm_enabled", False) for r in cfg.get("rules", {}).values())
    return render_template(
        "alarm2.html",
        alarm2_rows=alarm2_rows,
        no_alarms_configured=not any_configured,
        config_ok=bool(config.AZURE_LOG_ANALYTICS_WORKSPACE_ID),
        refreshed_at=datetime.now(LONDON_TZ).strftime("%d %b %Y  %H:%M:%S %Z"),
        data_is_stale=cache.is_cache_stale("alarm2"),
    )


def alarm3_page() -> str:
    """Render the Failures Alarm status page (Alarm 3)."""
    alarm3_rows = cache.cached_nowait(
        "alarm3",
        get_alarm3_status,
        ttl=config.API_CACHE_TTL,
    )
    cfg = load_alarm3_config()
    any_configured = any(r.get("alarm_enabled", False) for r in cfg.get("rules", {}).values())
    return render_template(
        "alarm3.html",
        alarm3_rows=alarm3_rows,
        no_alarms_configured=not any_configured,
        config_ok=bool(config.AZURE_LOG_ANALYTICS_WORKSPACE_ID),
        refreshed_at=datetime.now(LONDON_TZ).strftime("%d %b %Y  %H:%M:%S %Z"),
        data_is_stale=cache.is_cache_stale("alarm3"),
    )


def register(app: Flask) -> None:
    """Register every alarm page/pause/unpause route onto ``app`` with its original flat endpoint name."""
    app.add_url_rule("/alarms", endpoint="alarms_overview_page", view_func=alarms_overview_page)
    app.add_url_rule("/alarms/inactivity", endpoint="alarm_page", view_func=alarm_page)
    app.add_url_rule("/alarms/outgoing-messages", endpoint="alarm2_page", view_func=alarm2_page)
    app.add_url_rule("/alarms/failures", endpoint="alarm3_page", view_func=alarm3_page)
    app.add_url_rule(
        "/alarm1/pause/<rule_id>", endpoint="alarm1_pause", view_func=alarm1_pause, methods=["POST"]
    )
    app.add_url_rule(
        "/alarm1/unpause/<rule_id>", endpoint="alarm1_unpause", view_func=alarm1_unpause, methods=["POST"]
    )
    app.add_url_rule(
        "/alarm2/pause/<rule_id>", endpoint="alarm2_pause", view_func=alarm2_pause, methods=["POST"]
    )
    app.add_url_rule(
        "/alarm2/unpause/<rule_id>", endpoint="alarm2_unpause", view_func=alarm2_unpause, methods=["POST"]
    )
    app.add_url_rule(
        "/alarm3/pause/<rule_id>", endpoint="alarm3_pause", view_func=alarm3_pause, methods=["POST"]
    )
    app.add_url_rule(
        "/alarm3/unpause/<rule_id>", endpoint="alarm3_unpause", view_func=alarm3_unpause, methods=["POST"]
    )
