"""Alarm configuration pages (GET/POST) for Alarms 1-3.

Extracted from ``dashboard.app`` as part of the route-module split. These are
plain view functions (no Flask ``Blueprint`` — see ``dashboard.routes``
module docstring for why), registered onto the app by ``register(app)`` with
explicit endpoint names matching their original flat names so existing
``url_for(...)`` calls and any programmatic references keep working
unchanged.
"""

from __future__ import annotations

from flask import Flask, render_template, request

import dashboard.config as config
from dashboard.services import cache
from dashboard.services.alarm1 import (
    generate_rule_id as generate_alarm1_rule_id,
)
from dashboard.services.alarm1 import (
    get_config_page_data,
    load_alarm_config,
    save_alarm_config,
)
from dashboard.services.alarm2 import (
    generate_rule_id,
    get_alarm2_config_page_data,
    load_alarm2_config,
    save_alarm2_config,
)
from dashboard.services.alarm3 import (
    generate_rule_id as generate_alarm3_rule_id,
)
from dashboard.services.alarm3 import (
    get_alarm3_config_page_data,
    load_alarm3_config,
    save_alarm3_config,
)
from dashboard.services.form_utils import parse_int_form_field
from dashboard.services.status_builder import email_alerts_configured


def alarm_config_page() -> str:
    """Render and process the Inactivity Alarm configuration page (Alarm 1).

    GET  – displays the current rule list.
    POST – applies deletions, updates existing rules, and optionally adds a new rule.
    """
    saved = False
    new_rid: str | None = None

    if request.method == "POST":
        cfg = load_alarm_config()
        rules_cfg = cfg.setdefault("rules", {})

        # Handle deletions
        for key in list(request.form):
            if key.startswith("delete_"):
                rid = key[len("delete_") :]
                rules_cfg.setdefault(rid, {})["deleted"] = True

        # Update existing rules
        submitted_ids = [key[len("alerting_gap_") :] for key in request.form if key.startswith("alerting_gap_")]
        for rid in submitted_ids:
            if rules_cfg.get(rid, {}).get("deleted"):
                continue
            entry = rules_cfg.setdefault(rid, {})
            entry["alarm_enabled"] = f"enabled_{rid}" in request.form
            entry["email_alerts_enabled"] = f"email_{rid}" in request.form
            entry["email_ooh_enabled"] = f"email_ooh_{rid}" in request.form and entry["email_alerts_enabled"]
            entry["display_name"] = (request.form.get(f"display_name_{rid}") or "").strip()
            entry["workflow_id"] = (request.form.get(f"workflow_id_{rid}") or "").strip()
            entry["alerting_gap_minutes"] = parse_int_form_field(request.form, f"alerting_gap_{rid}", 60)
            entry["day_threshold_minutes"] = parse_int_form_field(request.form, f"day_threshold_{rid}", 60)
            entry["evening_threshold_minutes"] = parse_int_form_field(request.form, f"evening_threshold_{rid}", 120)
            entry["weekend_threshold_minutes"] = parse_int_form_field(request.form, f"weekend_threshold_{rid}", 240)

        # Add new rule
        new_wid = (request.form.get("new_workflow_id") or "").strip()
        new_rid = None
        if new_wid:
            new_rid = generate_alarm1_rule_id(new_wid, set(rules_cfg))
            rules_cfg[new_rid] = {
                "display_name": (request.form.get("new_display_name") or "").strip(),
                "alarm_enabled": "new_enabled" in request.form,
                "workflow_id": new_wid,
                "day_threshold_minutes": parse_int_form_field(request.form, "new_day_threshold", 60),
                "evening_threshold_minutes": parse_int_form_field(request.form, "new_evening_threshold", 120),
                "weekend_threshold_minutes": parse_int_form_field(request.form, "new_weekend_threshold", 240),
                "alerting_gap_minutes": parse_int_form_field(request.form, "new_alerting_gap", 60),
                "email_alerts_enabled": False,
                "email_ooh_enabled": False,
            }

        save_alarm_config(cfg)
        with cache.cache_lock:
            cache.cache_data["alarms"]["ts"] = 0.0
            cache.cache_data["alarms"]["data"] = None
        saved = True

    rules = get_config_page_data()
    return render_template(
        "alarm_config.html",
        rules=rules,
        saved=saved,
        new_rule_id=new_rid if request.method == "POST" else None,
        config_ok=bool(config.AZURE_LOG_ANALYTICS_WORKSPACE_ID),
        smtp_configured=email_alerts_configured(),
    )


def alarm2_config_page() -> str:
    """Render and process the Outgoing Messages Alarm configuration page (Alarm 2).

    GET  – displays the current rule list.
    POST – applies deletions, updates existing rules, and optionally adds a new rule.
    """
    saved = False
    new_id: str | None = None

    if request.method == "POST":
        cfg = load_alarm2_config()
        rules_cfg = cfg.setdefault("rules", {})

        # --- Handle deletions first ---
        for key in list(request.form):
            if key.startswith("delete_"):
                rid = key[len("delete_") :]
                rules_cfg.setdefault(rid, {})["deleted"] = True

        # --- Update existing rules (skip deleted) ---
        submitted_ids = [key[len("alerting_gap_") :] for key in request.form if key.startswith("alerting_gap_")]
        for rid in submitted_ids:
            if rules_cfg.get(rid, {}).get("deleted"):
                continue
            entry = rules_cfg.setdefault(rid, {})
            entry["alarm_enabled"] = f"enabled_{rid}" in request.form
            entry["email_alerts_enabled"] = f"email_{rid}" in request.form
            entry["email_ooh_enabled"] = f"email_ooh_{rid}" in request.form and entry["email_alerts_enabled"]
            entry["display_name"] = (request.form.get(f"display_name_{rid}") or "").strip()
            entry["workflow_id"] = (request.form.get(f"workflow_id_{rid}") or "").strip()
            entry["day_threshold_minutes"] = parse_int_form_field(request.form, f"day_threshold_{rid}", 60, minimum=0)
            entry["evening_threshold_minutes"] = parse_int_form_field(
                request.form, f"evening_threshold_{rid}", 120, minimum=0
            )
            entry["weekend_threshold_minutes"] = parse_int_form_field(
                request.form, f"weekend_threshold_{rid}", 240, minimum=0
            )
            entry["alerting_gap_minutes"] = parse_int_form_field(request.form, f"alerting_gap_{rid}", 60, minimum=1)

        # --- Add new rule if submitted ---
        new_wid = (request.form.get("new_workflow_id") or "").strip()
        new_id = None
        if new_wid:
            new_id = generate_rule_id(new_wid, set(rules_cfg))
            rules_cfg[new_id] = {
                "display_name": (request.form.get("new_display_name") or "").strip() or new_wid,
                "alarm_enabled": "new_enabled" in request.form,
                "workflow_id": new_wid,
                "day_threshold_minutes": parse_int_form_field(request.form, "new_day_threshold", 60, minimum=0),
                "evening_threshold_minutes": parse_int_form_field(
                    request.form, "new_evening_threshold", 120, minimum=0
                ),
                "weekend_threshold_minutes": parse_int_form_field(
                    request.form, "new_weekend_threshold", 240, minimum=0
                ),
                "alerting_gap_minutes": parse_int_form_field(request.form, "new_alerting_gap", 60, minimum=1),
                "email_alerts_enabled": False,
                "email_ooh_enabled": False,
            }

        save_alarm2_config(cfg)
        with cache.cache_lock:
            cache.cache_data["alarm2"]["ts"] = 0.0
            cache.cache_data["alarm2"]["data"] = None
        saved = True

    rules = get_alarm2_config_page_data()
    return render_template(
        "alarm2_config.html",
        rules=rules,
        saved=saved,
        new_rule_id=new_id if request.method == "POST" else None,
        config_ok=bool(config.AZURE_LOG_ANALYTICS_WORKSPACE_ID),
        smtp_configured=email_alerts_configured(),
    )


def alarm3_config_page() -> str:
    """Render and process the Failures Alarm configuration page (Alarm 3).

    GET  – displays the current rule list.
    POST – applies deletions, updates existing rules, and optionally adds a new rule.
    """
    saved = False
    new_id: str | None = None

    if request.method == "POST":
        cfg = load_alarm3_config()
        rules_cfg = cfg.setdefault("rules", {})

        for key in list(request.form):
            if key.startswith("delete_"):
                rid = key[len("delete_") :]
                rules_cfg.setdefault(rid, {})["deleted"] = True

        submitted_ids = [key[len("alerting_gap_") :] for key in request.form if key.startswith("alerting_gap_")]
        for rid in submitted_ids:
            if rules_cfg.get(rid, {}).get("deleted"):
                continue
            entry = rules_cfg.setdefault(rid, {})
            entry["alarm_enabled"] = f"enabled_{rid}" in request.form
            entry["email_alerts_enabled"] = f"email_{rid}" in request.form
            entry["email_ooh_enabled"] = f"email_ooh_{rid}" in request.form and entry["email_alerts_enabled"]
            entry["display_name"] = (request.form.get(f"display_name_{rid}") or "").strip()
            entry["workflow_id"] = (request.form.get(f"workflow_id_{rid}") or "").strip()
            entry["window_duration_minutes"] = parse_int_form_field(
                request.form, f"window_duration_{rid}", 15, minimum=1
            )
            entry["threshold"] = parse_int_form_field(request.form, f"threshold_{rid}", 1, minimum=1)
            entry["alerting_gap_minutes"] = parse_int_form_field(request.form, f"alerting_gap_{rid}", 60, minimum=1)

        new_wid = (request.form.get("new_workflow_id") or "").strip()
        new_id = None
        if new_wid:
            new_id = generate_alarm3_rule_id(new_wid, set(rules_cfg))
            rules_cfg[new_id] = {
                "display_name": (request.form.get("new_display_name") or "").strip() or f"{new_wid} Failures",
                "alarm_enabled": "new_enabled" in request.form,
                "workflow_id": new_wid,
                "window_duration_minutes": parse_int_form_field(request.form, "new_window_duration", 15, minimum=1),
                "threshold": parse_int_form_field(request.form, "new_threshold", 1, minimum=1),
                "alerting_gap_minutes": parse_int_form_field(request.form, "new_alerting_gap", 60, minimum=1),
                "email_alerts_enabled": False,
                "email_ooh_enabled": False,
            }

        save_alarm3_config(cfg)
        with cache.cache_lock:
            cache.cache_data["alarm3"]["ts"] = 0.0
            cache.cache_data["alarm3"]["data"] = None
        saved = True

    rules = get_alarm3_config_page_data()
    return render_template(
        "alarm3_config.html",
        rules=rules,
        saved=saved,
        new_rule_id=new_id if request.method == "POST" else None,
        config_ok=bool(config.AZURE_LOG_ANALYTICS_WORKSPACE_ID),
        smtp_configured=email_alerts_configured(),
    )


def register(app: Flask) -> None:
    """Register every alarm-config route onto ``app`` with its original flat endpoint name."""
    app.add_url_rule(
        "/alarm-config", endpoint="alarm_config_page", view_func=alarm_config_page, methods=["GET", "POST"]
    )
    app.add_url_rule(
        "/alarm2-config", endpoint="alarm2_config_page", view_func=alarm2_config_page, methods=["GET", "POST"]
    )
    app.add_url_rule(
        "/alarm3-config", endpoint="alarm3_config_page", view_func=alarm3_config_page, methods=["GET", "POST"]
    )
