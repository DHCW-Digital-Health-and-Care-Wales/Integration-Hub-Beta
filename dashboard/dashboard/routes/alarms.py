"""Alarm overview/status pages, alarm pause actions and the Alarm Pauses page/API.

Extracted from ``dashboard.app`` as part of the route-module split. These are
plain view functions (no Flask ``Blueprint`` — see ``dashboard.routes``
module docstring for why), registered onto the app by ``register(app)`` with
explicit endpoint names matching their original flat names so existing
``url_for(...)`` calls and any programmatic references keep working
unchanged.

Pause endpoints:

  * ``POST /alarmN/pause/<rule_id>`` / ``POST /alarmN/unpause/<rule_id>`` — start-now
    pause / resume of a single rule (used by the alarm tables' Pause/Resume buttons).
  * ``GET /alarms/pauses`` — page listing active, scheduled and recently ended pauses.
  * ``GET /api/alarm-pauses`` — the same lists as JSON.
  * ``GET /api/alarm-pauses/options`` — flow/rule picker data for the pause modal.
  * ``POST /api/alarm-pauses`` — create a pause (any scope, now or scheduled).
  * ``POST /api/alarm-pauses/<pause_id>/cancel`` — cancel a scheduled pause or end an active one.

Pause storage and rules live in :mod:`dashboard.services.alarm_pauses`; after any
change the cached alarm rows are re-patched so the reloaded page is correct immediately.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from flask import Flask, Response, current_app, jsonify, render_template, request, url_for

import dashboard.config as config
from dashboard.services import alarm_base, alarm_pauses, cache, cosmos_store
from dashboard.services.alarm1 import (
    get_alarm_status,
    get_config_page_data,
    load_alarm_config,
    pause_alarm_rule,
    unpause_alarm_rule,
)
from dashboard.services.alarm2 import (
    get_alarm2_config_page_data,
    get_alarm2_status,
    load_alarm2_config,
    pause_alarm2_rule,
    unpause_alarm2_rule,
)
from dashboard.services.alarm3 import (
    get_alarm3_config_page_data,
    get_alarm3_status,
    load_alarm3_config,
    pause_alarm3_rule,
    unpause_alarm3_rule,
)
from dashboard.services.flows import build_flow_options, get_flows
from dashboard.services.status_builder import LONDON_TZ

# Sort order used to bubble paused/critical rows to the top of alarm tables.
_PAUSE_ORDER = {"paused": 0, "critical": 1, "suppressed": 2, "unknown": 3, "healthy": 4}

# Alarm type -> in-memory cache key holding that alarm's evaluated status rows.
ALARM_CACHE_KEYS = {"alarm1": "alarms", "alarm2": "alarm2", "alarm3": "alarm3"}
# Short alarm-type names used when labelling rule targets on the pauses page/modal.
ALARM_TYPE_LABELS = {"alarm1": "Inactivity", "alarm2": "Volume", "alarm3": "Failures"}


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
        pause_summary=alarm_pauses.current_summary(),
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


def _patch_cached_rows(resumed: tuple[str, str] | None = None) -> None:
    """Re-apply pause records to the cached alarm rows so the next page load reflects a change instantly.

    ``resumed`` names an ``(alarm_type, rule_id)`` whose legacy pause was just cleared.
    The caches are then marked stale so a background refresh re-evaluates the true status.
    """
    pauses = alarm_pauses.list_pauses()
    now = datetime.now(timezone.utc)
    with cache.cache_lock:
        for alarm_type, key in ALARM_CACHE_KEYS.items():
            entry = cache.cache_data.get(key)
            if not entry or not isinstance(entry.get("data"), list):
                continue
            rows: list[dict] = entry["data"]
            for row in rows:
                wid = (row.get("workflow_id") or "").strip()
                pause = alarm_pauses.active_pause_for(pauses, alarm_type, row.get("id", ""), wid, now)
                if pause is not None:
                    row.update(status="paused", **alarm_pauses.pause_row_fields(pause, now))
                elif row.get("status") == "paused" and (
                    row.get("pause_id") or resumed == (alarm_type, row.get("id"))
                ):
                    row.update(status="unknown", **alarm_base.EMPTY_PAUSE_FIELDS)
            alarm_pauses.annotate_scheduled(rows, alarm_type, pauses, now)
            rows.sort(key=lambda r: _PAUSE_ORDER.get(r.get("status", ""), 9))
            entry["ts"] = 0.0


def _pause_error_response(exc: Exception) -> tuple[Response, int]:
    """Map pause-service exceptions to a JSON error response.

    409 = rule is covered by a wider pause (includes a ``manage_url`` to that pause),
    404 = unknown pause id, 400 = validation failure, 503 = pause storage unavailable.
    """
    if isinstance(exc, alarm_pauses.PauseConflictError):
        return (
            jsonify(
                {
                    "ok": False,
                    "error": exc.safe_message,
                    "pause_id": exc.pause_id,
                    "manage_url": url_for("alarm_pauses_page", _anchor=f"pause-{exc.pause_id}"),
                }
            ),
            409,
        )
    if isinstance(exc, alarm_pauses.PauseNotFoundError):
        return jsonify({"ok": False, "error": exc.safe_message}), 404
    if isinstance(exc, alarm_pauses.PauseError):
        return jsonify({"ok": False, "error": exc.safe_message}), 400
    if isinstance(exc, alarm_pauses.PausePersistenceError):
        current_app.logger.error("Alarm pause persistence failure: %s", exc)
        return jsonify({"ok": False, "error": exc.safe_message}), 503
    raise exc


# Exceptions the pause service raises for expected, user-facing failures.
_PAUSE_EXCEPTIONS = (alarm_pauses.PauseError, alarm_pauses.PausePersistenceError)


def _pause_now(pause_fn: Callable[[str, int | None, str, str], dict], rule_id: str) -> tuple[Response, int] | Response:
    """Handle a start-now single-rule pause request.

    Expects ``{"duration_minutes": int, "indefinite": bool, "reason": str, "requested_by": str}``.
    ``duration_minutes`` defaults to 60 (the previous behaviour) and is ignored when
    ``indefinite`` is true. ``pause_fn`` is the alarm module's ``pause_alarm*_rule``.
    """
    data = request.get_json(silent=True) or {}
    duration: int | None = None
    if not data.get("indefinite"):
        try:
            duration = int(data.get("duration_minutes", 60))
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "Invalid duration_minutes value."}), 400
    try:
        pause = pause_fn(rule_id, duration, str(data.get("reason", "")), str(data.get("requested_by", "")))
    except _PAUSE_EXCEPTIONS as exc:
        return _pause_error_response(exc)
    _patch_cached_rows()
    return jsonify({"ok": True, "pause": pause})


def _resume(alarm_type: str, resume_fn: Callable[[str], None], rule_id: str) -> tuple[Response, int] | Response:
    """Handle a single-rule resume request.

    ``resume_fn`` is the alarm module's ``unpause_alarm*_rule``; it raises
    ``PauseConflictError`` (-> 409) when the rule is paused by a flow/all-flows pause.
    """
    try:
        resume_fn(rule_id)
    except _PAUSE_EXCEPTIONS as exc:
        return _pause_error_response(exc)
    _patch_cached_rows(resumed=(alarm_type, rule_id))
    return jsonify({"ok": True})


def alarm1_pause(rule_id: str) -> tuple[Response, int] | Response:
    """Pause an Alarm 1 rule from now."""
    return _pause_now(pause_alarm_rule, rule_id)


def alarm1_unpause(rule_id: str) -> tuple[Response, int] | Response:
    """Resume an Alarm 1 rule."""
    return _resume("alarm1", unpause_alarm_rule, rule_id)


def alarm2_pause(rule_id: str) -> tuple[Response, int] | Response:
    """Pause an Alarm 2 rule from now."""
    return _pause_now(pause_alarm2_rule, rule_id)


def alarm2_unpause(rule_id: str) -> tuple[Response, int] | Response:
    """Resume an Alarm 2 rule."""
    return _resume("alarm2", unpause_alarm2_rule, rule_id)


def alarm3_pause(rule_id: str) -> tuple[Response, int] | Response:
    """Pause an Alarm 3 rule from now."""
    return _pause_now(pause_alarm3_rule, rule_id)


def alarm3_unpause(rule_id: str) -> tuple[Response, int] | Response:
    """Resume an Alarm 3 rule."""
    return _resume("alarm3", unpause_alarm3_rule, rule_id)


def _rule_catalogue() -> dict[str, list[dict]]:
    """Return every non-deleted rule per alarm type (for validation and the pause modal)."""
    return {
        "alarm1": get_config_page_data(),
        "alarm2": get_alarm2_config_page_data(),
        "alarm3": get_alarm3_config_page_data(),
    }


def _label_targets(views: list[dict], flow_labels: dict[str, str], catalogue: dict[str, list[dict]]) -> None:
    """Add human-readable ``target_labels`` to pause views in place."""
    rule_labels = {
        (alarm_type, r["id"]): r.get("display_name") or r["id"]
        for alarm_type, rules in catalogue.items()
        for r in rules
    }
    for view in views:
        if view["scope_type"] == alarm_pauses.SCOPE_FLOWS:
            view["target_labels"] = [flow_labels.get(wid, wid) for wid in view["targets"]]
        elif view["scope_type"] == alarm_pauses.SCOPE_RULE:
            view["target_labels"] = [
                f"{ALARM_TYPE_LABELS.get(t.get('alarm_type', ''), t.get('alarm_type', ''))}: "
                f"{rule_labels.get((t.get('alarm_type'), t.get('rule_id')), t.get('rule_id'))}"
                for t in view["targets"]
            ]
        else:
            view["target_labels"] = []


def _pause_page_context() -> dict:
    """Build the grouped pause lists plus picker data shared by the page and JSON API."""
    catalogue = _rule_catalogue()
    flow_options = build_flow_options(get_flows(), [r for rules in catalogue.values() for r in rules])
    flow_labels = {o["id"]: o["label"] for o in flow_options}
    now = datetime.now(timezone.utc)
    pauses = alarm_pauses.list_pauses()
    groups = alarm_pauses.group_for_display(pauses, now)
    for views in groups.values():
        _label_targets(views, flow_labels, catalogue)
    return {
        "groups": groups,
        "summary": alarm_pauses.summarise(pauses, now),
        "flow_options": flow_options,
        "rule_options": [
            {
                "alarm_type": alarm_type,
                "rule_id": r["id"],
                "label": f"{ALARM_TYPE_LABELS[alarm_type]}: {r.get('display_name') or r['id']}",
                "workflow_id": r.get("workflow_id", ""),
            }
            for alarm_type, rules in catalogue.items()
            for r in rules
        ],
    }


def alarm_pauses_page() -> str:
    """Render the Alarm Pauses page (active, scheduled and recently ended pauses)."""
    return render_template(
        "alarm_pauses.html",
        **_pause_page_context(),
        persistence_configured=cosmos_store.is_configured(),
        refreshed_at=datetime.now(LONDON_TZ).strftime("%d %b %Y  %H:%M:%S %Z"),
    )


def api_alarm_pauses_list() -> Response:
    """JSON list of pauses grouped as active / scheduled / recent, plus summary counts."""
    context = _pause_page_context()
    return jsonify({"groups": context["groups"], "summary": context["summary"]})


def api_alarm_pauses_options() -> Response:
    """JSON flow and rule picker options for the shared pause modal.

    Served separately (and fetched lazily by ``alarm-pause.js``) so every page that
    includes the modal doesn't have to run flow discovery on render.
    """
    context = _pause_page_context()
    return jsonify({"flow_options": context["flow_options"], "rule_options": context["rule_options"]})


def api_alarm_pauses_create() -> tuple[Response, int] | Response:
    """Create a pause of any scope, starting now or at a scheduled time.

    Body (see ``alarm_pauses.build_pause``)::

        {"scope_type": "rule" | "flows" | "all",
         "targets": [{"alarm_type": "alarm1", "rule_id": "..."}] | ["<workflow_id>", ...] | [],
         "start": null | "YYYY-MM-DDTHH:MM" (UK time),
         "end_mode": "duration" | "until" | "indefinite",
         "duration_minutes": int, "end": "YYYY-MM-DDTHH:MM",
         "reason": str, "requested_by": str}

    Returns 201 with the created pause view.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"ok": False, "error": "Expected a JSON object."}), 400
    known_rules = {
        alarm_type: {r["id"]: (r.get("workflow_id") or "").strip() for r in rules}
        for alarm_type, rules in _rule_catalogue().items()
    }
    try:
        pause = alarm_pauses.create_pause(data, known_rules)
    except _PAUSE_EXCEPTIONS as exc:
        return _pause_error_response(exc)
    _patch_cached_rows()
    return jsonify({"ok": True, "pause": pause}), 201


def api_alarm_pauses_cancel(pause_id: str) -> tuple[Response, int] | Response:
    """Cancel a scheduled pause or end an active one now."""
    try:
        pause = alarm_pauses.cancel_pause(pause_id)
    except _PAUSE_EXCEPTIONS as exc:
        return _pause_error_response(exc)
    _patch_cached_rows()
    return jsonify({"ok": True, "pause": pause})


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


def _rows_for_flow(status_rows: list[dict] | None, cfg_rows: list[dict], workflow_id: str) -> list[dict]:
    """Return live status rows for ``workflow_id``, plus configured rules missing from the live status.

    Status rows only cover enabled rules (and are absent on a cold cache), so config rows
    fill the gap: disabled rules get status ``disabled``, enabled-but-not-yet-evaluated get ``unknown``.
    """
    matched = [r for r in (status_rows or []) if (r.get("workflow_id") or "").strip() == workflow_id]
    seen = {r.get("id") for r in matched}
    for cfg in cfg_rows:
        if (cfg.get("workflow_id") or "").strip() != workflow_id or cfg.get("id") in seen:
            continue
        matched.append({**cfg, "status": "unknown" if cfg.get("alarm_enabled") else "disabled"})
    return matched


def alarms_by_flow_page() -> str:
    """Render the View by Flow page showing Alarms 1-3 for a single selected flow."""
    cfg1 = get_config_page_data()
    cfg2 = get_alarm2_config_page_data()
    cfg3 = get_alarm3_config_page_data()
    flow_options = build_flow_options(get_flows(), cfg1 + cfg2 + cfg3)

    requested = request.args.get("flow", "").strip()
    selected_flow = next((o for o in flow_options if o["id"] == requested), None)

    alarm1_rows: list[dict] = []
    alarm2_rows: list[dict] = []
    alarm3_rows: list[dict] = []
    if selected_flow:
        a1_status, a2_status, a3_status = cache.multi_cached_nowait(
            [
                ("alarms", get_alarm_status, config.API_CACHE_TTL),
                ("alarm2", get_alarm2_status, config.API_CACHE_TTL),
                ("alarm3", get_alarm3_status, config.API_CACHE_TTL),
            ]
        )
        alarm1_rows = _rows_for_flow(a1_status, cfg1, selected_flow["id"])
        alarm2_rows = _rows_for_flow(a2_status, cfg2, selected_flow["id"])
        alarm3_rows = _rows_for_flow(a3_status, cfg3, selected_flow["id"])

    return render_template(
        "alarms_by_flow.html",
        flow_options=flow_options,
        selected_flow=selected_flow,
        alarm1_rows=alarm1_rows,
        alarm2_rows=alarm2_rows,
        alarm3_rows=alarm3_rows,
        config_ok=bool(config.AZURE_LOG_ANALYTICS_WORKSPACE_ID),
        refreshed_at=datetime.now(LONDON_TZ).strftime("%d %b %Y  %H:%M:%S %Z"),
    )


def register(app: Flask) -> None:
    """Register every alarm page/pause/unpause route onto ``app`` with its original flat endpoint name."""
    app.add_url_rule("/alarms", endpoint="alarms_overview_page", view_func=alarms_overview_page)
    app.add_url_rule("/alarms/by-flow", endpoint="alarms_by_flow_page", view_func=alarms_by_flow_page)
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
    app.add_url_rule("/alarms/pauses", endpoint="alarm_pauses_page", view_func=alarm_pauses_page)
    app.add_url_rule("/api/alarm-pauses", endpoint="api_alarm_pauses_list", view_func=api_alarm_pauses_list)
    app.add_url_rule(
        "/api/alarm-pauses/options", endpoint="api_alarm_pauses_options", view_func=api_alarm_pauses_options
    )
    app.add_url_rule(
        "/api/alarm-pauses", endpoint="api_alarm_pauses_create", view_func=api_alarm_pauses_create, methods=["POST"]
    )
    app.add_url_rule(
        "/api/alarm-pauses/<pause_id>/cancel",
        endpoint="api_alarm_pauses_cancel",
        view_func=api_alarm_pauses_cancel,
        methods=["POST"],
    )
