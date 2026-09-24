"""Per-flow alarm configuration page (GET/POST) for Alarms 1-3.

Alarm rules are grouped by flow (``workflow_id``) rather than by alarm type: one
screen shows and edits every Alarm 1, 2 and 3 rule for the selected flow, and new
rules are added for that flow from the same screen. Plain view functions (no
Flask ``Blueprint`` — see ``dashboard.routes`` module docstring for why),
registered by ``register(app)``.

Form fields for each alarm type are namespaced with ``a1-``/``a2-``/``a3-``
because rule ids are generated independently per alarm type and can collide.
The retired per-alarm URLs (``/alarm-config`` etc.) redirect here and keep their
endpoint names so existing ``url_for(...)`` references still resolve.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from flask import Flask, abort, redirect, render_template, request, url_for
from werkzeug.datastructures import ImmutableMultiDict, MultiDict
from werkzeug.wrappers import Response

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
from dashboard.services.flows import build_flow_options, get_flows
from dashboard.services.form_utils import parse_int_form_field
from dashboard.services.status_builder import email_alerts_configured

ALARM_PREFIXES: dict[int, str] = {1: "a1-", 2: "a2-", 3: "a3-"}

# Custom workflow ids must survive the alarms' KQL sanitiser ([^a-zA-Z0-9_-] is stripped) unchanged.
_WORKFLOW_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,119}")

ApplyFn = Callable[[ImmutableMultiDict, dict], str | None]


# ---------------------------------------------------------------------------
# Form application — one function per alarm type, operating on an un-prefixed form
# ---------------------------------------------------------------------------


def _scoped_form(form: MultiDict, prefix: str) -> ImmutableMultiDict:
    """Return the fields starting with ``prefix``, with the prefix stripped."""
    return ImmutableMultiDict([(k[len(prefix) :], v) for k, v in form.items(multi=True) if k.startswith(prefix)])


def _apply_deletions(form: ImmutableMultiDict, rules_cfg: dict) -> None:
    for key in form:
        if key.startswith("delete_"):
            rules_cfg.setdefault(key[len("delete_") :], {})["deleted"] = True


def _submitted_rule_ids(form: ImmutableMultiDict, rules_cfg: dict) -> list[str]:
    ids = [key[len("alerting_gap_") :] for key in form if key.startswith("alerting_gap_")]
    return [rid for rid in ids if not rules_cfg.get(rid, {}).get("deleted")]


def _apply_common_fields(entry: dict, form: ImmutableMultiDict, rid: str) -> None:
    entry["alarm_enabled"] = f"enabled_{rid}" in form
    entry["email_alerts_enabled"] = f"email_{rid}" in form
    entry["email_ooh_enabled"] = f"email_ooh_{rid}" in form and entry["email_alerts_enabled"]
    entry["display_name"] = (form.get(f"display_name_{rid}") or "").strip()
    entry["workflow_id"] = (form.get(f"workflow_id_{rid}") or "").strip()


def _apply_alarm1_form(form: ImmutableMultiDict, rules_cfg: dict) -> str | None:
    """Apply Alarm 1 (inactivity) deletions/updates/addition; return the new rule id, if any."""
    _apply_deletions(form, rules_cfg)
    for rid in _submitted_rule_ids(form, rules_cfg):
        entry = rules_cfg.setdefault(rid, {})
        _apply_common_fields(entry, form, rid)
        entry["alerting_gap_minutes"] = parse_int_form_field(form, f"alerting_gap_{rid}", 60)
        entry["day_threshold_minutes"] = parse_int_form_field(form, f"day_threshold_{rid}", 60)
        entry["evening_threshold_minutes"] = parse_int_form_field(form, f"evening_threshold_{rid}", 120)
        entry["weekend_threshold_minutes"] = parse_int_form_field(form, f"weekend_threshold_{rid}", 240)

    new_wid = (form.get("new_workflow_id") or "").strip()
    if not new_wid:
        return None
    new_rid = generate_alarm1_rule_id(new_wid, set(rules_cfg))
    rules_cfg[new_rid] = {
        "display_name": (form.get("new_display_name") or "").strip(),
        "alarm_enabled": "new_enabled" in form,
        "workflow_id": new_wid,
        "day_threshold_minutes": parse_int_form_field(form, "new_day_threshold", 60),
        "evening_threshold_minutes": parse_int_form_field(form, "new_evening_threshold", 120),
        "weekend_threshold_minutes": parse_int_form_field(form, "new_weekend_threshold", 240),
        "alerting_gap_minutes": parse_int_form_field(form, "new_alerting_gap", 60),
        "email_alerts_enabled": False,
        "email_ooh_enabled": False,
    }
    return new_rid


def _apply_alarm2_form(form: ImmutableMultiDict, rules_cfg: dict) -> str | None:
    """Apply Alarm 2 (outgoing volume) deletions/updates/addition; return the new rule id, if any."""
    _apply_deletions(form, rules_cfg)
    for rid in _submitted_rule_ids(form, rules_cfg):
        entry = rules_cfg.setdefault(rid, {})
        _apply_common_fields(entry, form, rid)
        entry["day_threshold_minutes"] = parse_int_form_field(form, f"day_threshold_{rid}", 60, minimum=0)
        entry["evening_threshold_minutes"] = parse_int_form_field(form, f"evening_threshold_{rid}", 120, minimum=0)
        entry["weekend_threshold_minutes"] = parse_int_form_field(form, f"weekend_threshold_{rid}", 240, minimum=0)
        entry["alerting_gap_minutes"] = parse_int_form_field(form, f"alerting_gap_{rid}", 60, minimum=1)

    new_wid = (form.get("new_workflow_id") or "").strip()
    if not new_wid:
        return None
    new_rid = generate_rule_id(new_wid, set(rules_cfg))
    rules_cfg[new_rid] = {
        "display_name": (form.get("new_display_name") or "").strip() or new_wid,
        "alarm_enabled": "new_enabled" in form,
        "workflow_id": new_wid,
        "day_threshold_minutes": parse_int_form_field(form, "new_day_threshold", 60, minimum=0),
        "evening_threshold_minutes": parse_int_form_field(form, "new_evening_threshold", 120, minimum=0),
        "weekend_threshold_minutes": parse_int_form_field(form, "new_weekend_threshold", 240, minimum=0),
        "alerting_gap_minutes": parse_int_form_field(form, "new_alerting_gap", 60, minimum=1),
        "email_alerts_enabled": False,
        "email_ooh_enabled": False,
    }
    return new_rid


def _apply_alarm3_form(form: ImmutableMultiDict, rules_cfg: dict) -> str | None:
    """Apply Alarm 3 (failures) deletions/updates/addition; return the new rule id, if any."""
    _apply_deletions(form, rules_cfg)
    for rid in _submitted_rule_ids(form, rules_cfg):
        entry = rules_cfg.setdefault(rid, {})
        _apply_common_fields(entry, form, rid)
        entry["window_duration_minutes"] = parse_int_form_field(form, f"window_duration_{rid}", 15, minimum=1)
        entry["threshold"] = parse_int_form_field(form, f"threshold_{rid}", 1, minimum=1)
        entry["alerting_gap_minutes"] = parse_int_form_field(form, f"alerting_gap_{rid}", 60, minimum=1)

    new_wid = (form.get("new_workflow_id") or "").strip()
    if not new_wid:
        return None
    new_rid = generate_alarm3_rule_id(new_wid, set(rules_cfg))
    rules_cfg[new_rid] = {
        "display_name": (form.get("new_display_name") or "").strip() or f"{new_wid} Failures",
        "alarm_enabled": "new_enabled" in form,
        "workflow_id": new_wid,
        "window_duration_minutes": parse_int_form_field(form, "new_window_duration", 15, minimum=1),
        "threshold": parse_int_form_field(form, "new_threshold", 1, minimum=1),
        "alerting_gap_minutes": parse_int_form_field(form, "new_alerting_gap", 60, minimum=1),
        "email_alerts_enabled": False,
        "email_ooh_enabled": False,
    }
    return new_rid


def _alarm_handlers() -> dict[int, tuple[str, Callable[[], dict], Callable[[dict], None], ApplyFn]]:
    # Built per call (not at import) so tests can patch the module-level load/save names.
    return {
        1: ("alarms", load_alarm_config, save_alarm_config, _apply_alarm1_form),
        2: ("alarm2", load_alarm2_config, save_alarm2_config, _apply_alarm2_form),
        3: ("alarm3", load_alarm3_config, save_alarm3_config, _apply_alarm3_form),
    }


def save_flow_alarm_form(form: MultiDict) -> dict[int, str | None]:
    """Apply each alarm type's namespaced fields; only alarm types present in the form are saved.

    Returns ``{alarm_no: new_rule_id_or_None}`` for every alarm type that was saved.
    """
    new_ids: dict[int, str | None] = {}
    for alarm_no, (cache_key, load, save, apply) in _alarm_handlers().items():
        scoped = _scoped_form(form, ALARM_PREFIXES[alarm_no])
        if not scoped:
            continue
        cfg = load()
        new_ids[alarm_no] = apply(scoped, cfg.setdefault("rules", {}))
        save(cfg)
        with cache.cache_lock:
            cache.cache_data[cache_key]["ts"] = 0.0
            cache.cache_data[cache_key]["data"] = None
    return new_ids


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------


def _resolve_flow(requested: str, flow_options: list[dict[str, str]]) -> tuple[dict | None, bool]:
    """Return ``(selected_flow, invalid)`` for a requested workflow id.

    Known flows resolve to their option; an unknown but well-formed id is accepted as a
    new flow (``is_new``) so alarms can be added for flows not yet discovered.
    """
    if not requested:
        return None, False
    match = next((o for o in flow_options if o["id"] == requested), None)
    if match:
        return {**match, "is_new": False}, False
    if not _WORKFLOW_ID_RE.fullmatch(requested):
        return None, True
    return {"id": requested, "label": requested, "is_new": True}, False


def _rules_for_flow(rules: list[dict], workflow_id: str) -> list[dict]:
    return [r for r in rules if (r.get("workflow_id") or "").strip() == workflow_id]


def alarm_flow_config_page() -> str:
    """Render and process the per-flow alarm configuration screen (Alarms 1, 2 and 3).

    GET  – ``?flow=<workflow_id>`` shows that flow's rules for all three alarm types.
    POST – applies deletions/updates/additions for the selected flow, then re-renders.
    """
    requested = request.args.get("flow", "").strip()
    cfg_rows = get_config_page_data() + get_alarm2_config_page_data() + get_alarm3_config_page_data()
    selected_flow, flow_invalid = _resolve_flow(requested, build_flow_options(get_flows(), cfg_rows))

    saved = False
    new_rule_anchor: str | None = None
    if request.method == "POST":
        if selected_flow is None:
            abort(400)
        new_ids = save_flow_alarm_form(request.form)
        saved = True
        new_rule_anchor = next(
            (f"{ALARM_PREFIXES[n]}rule-{rid}" for n, rid in sorted(new_ids.items()) if rid), None
        )

    alarm1_rules = get_config_page_data()
    alarm2_rules = get_alarm2_config_page_data()
    alarm3_rules = get_alarm3_config_page_data()
    flow_options = build_flow_options(get_flows(), alarm1_rules + alarm2_rules + alarm3_rules)
    if selected_flow is not None:
        # Re-resolve so a newly added custom flow is no longer flagged as new.
        selected_flow, _ = _resolve_flow(selected_flow["id"], flow_options)

    flow_id = selected_flow["id"] if selected_flow else ""
    return render_template(
        "alarm_flow_config.html",
        flow_options=flow_options,
        selected_flow=selected_flow,
        flow_invalid=flow_invalid,
        alarm1_rules=_rules_for_flow(alarm1_rules, flow_id) if flow_id else [],
        alarm2_rules=_rules_for_flow(alarm2_rules, flow_id) if flow_id else [],
        alarm3_rules=_rules_for_flow(alarm3_rules, flow_id) if flow_id else [],
        saved=saved,
        new_rule_anchor=new_rule_anchor,
        config_ok=bool(config.AZURE_LOG_ANALYTICS_WORKSPACE_ID),
        smtp_configured=email_alerts_configured(),
    )


def legacy_alarm_config_redirect() -> Response:
    """Redirect the retired per-alarm config URLs to the per-flow screen, preserving ``?flow=``."""
    flow = request.args.get("flow", "").strip()
    return redirect(url_for("alarm_flow_config_page", flow=flow or None))


def register(app: Flask) -> None:
    """Register the per-flow alarm config route and the legacy per-alarm redirects onto ``app``."""
    app.add_url_rule(
        "/alarms/config",
        endpoint="alarm_flow_config_page",
        view_func=alarm_flow_config_page,
        methods=["GET", "POST"],
    )
    for url, endpoint in (
        ("/alarm-config", "alarm_config_page"),
        ("/alarm2-config", "alarm2_config_page"),
        ("/alarm3-config", "alarm3_config_page"),
    ):
        app.add_url_rule(url, endpoint=endpoint, view_func=legacy_alarm_config_redirect)
