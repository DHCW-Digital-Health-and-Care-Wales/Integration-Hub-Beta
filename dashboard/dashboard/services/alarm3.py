"""Alarm 3 service — message processing failure monitoring.

Config is persisted to ``alarm3_config.json`` in the dashboard root directory.
State (last alarm fired time per rule) is persisted to ``alarm3_state.json``.

Each rule monitors MESSAGE_FAILED events for a specific workflow_id and has
the following settings:
  alarm_enabled            – bool, whether Alarm 3 is active for this rule
  display_name             – human-readable label
  workflow_id              – customDimensions["workflow_id"] filter value
  window_duration_minutes  – lookback window for the failure count query
  threshold                – fire when MESSAGE_FAILED count >= this value
  alerting_gap_minutes     – cooldown before the alarm re-fires
  email_alerts_enabled     – bool, whether to send email on alarm

Status values returned per rule:
  'critical'   – failure count at/above threshold, cooldown has expired
  'suppressed' – failure count at/above threshold but within cooldown
  'healthy'    – failure count below threshold
  'unknown'    – query failed or no Log Analytics workspace configured
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from azure.monitor.query import LogsQueryClient, LogsQueryStatus

from dashboard import config
from dashboard.services.credentials import get_azure_credential
from dashboard.services.email_service import send_alert_email

log = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent.parent.parent / "alarm3_config.json"
STATE_PATH = Path(__file__).parent.parent.parent / "alarm3_state.json"

DEFAULT_WINDOW_MINUTES = 15
DEFAULT_THRESHOLD = 1
DEFAULT_ALERTING_GAP = 60

KNOWN_RULES: list[dict] = [
    {
        "id": "phw-to-mpi-failures",
        "display_name": "PHW → MPI Failures",
        "workflow_id": "phw-to-mpi",
    },
]


# ---------------------------------------------------------------------------
# Config / state persistence
# ---------------------------------------------------------------------------


def load_alarm3_config() -> dict:
    """Load Alarm 3 config from JSON. Returns empty config on missing/corrupt file."""
    if not CONFIG_PATH.exists():
        return {"rules": {}}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Failed to load alarm3 config: %s", exc)
        return {"rules": {}}


def save_alarm3_config(cfg: dict) -> None:
    """Persist Alarm 3 config to JSON."""
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, default=str), encoding="utf-8")


def _load_alarm3_state() -> dict:
    """Load per-rule Alarm 3 state (last_alarm_at timestamps) from JSON. Returns empty state on missing/corrupt file."""
    if not STATE_PATH.exists():
        return {"rules": {}}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Failed to load alarm3 state: %s", exc)
        return {"rules": {}}


def _save_alarm3_state(state: dict) -> None:
    """Persist per-rule Alarm 3 state to JSON, logging errors without raising."""
    try:
        STATE_PATH.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    except OSError as exc:
        log.error("Failed to save alarm3 state: %s", exc)


# ---------------------------------------------------------------------------
# Pause / unpause helpers
# ---------------------------------------------------------------------------


def pause_alarm3_rule(rule_id: str, duration_minutes: int, reason: str = "") -> None:
    """Pause a specific Alarm 3 rule for ``duration_minutes``.

    Writes ``paused_until`` (ISO timestamp) and ``pause_reason`` into the rule's
    state entry.  The alarm evaluator will skip the rule and return ``status='paused'``
    until that time has elapsed.
    """
    state = _load_alarm3_state()
    state_rules = state.setdefault("rules", {})
    now = datetime.now(timezone.utc)
    paused_until = now + timedelta(minutes=duration_minutes)
    state_rules.setdefault(rule_id, {}).update(
        {
            "paused_until": paused_until.isoformat(),
            "pause_reason": reason.strip(),
        }
    )
    _save_alarm3_state(state)
    log.info(
        "Alarm 3 rule %s paused for %d minutes (until %s). Reason: %s",
        rule_id,
        duration_minutes,
        paused_until.isoformat(),
        reason or "(none)",
    )


def unpause_alarm3_rule(rule_id: str) -> None:
    """Remove a manual pause from a specific Alarm 3 rule, restoring normal evaluation."""
    state = _load_alarm3_state()
    state_rules = state.get("rules", {})
    rule_state = state_rules.get(rule_id, {})
    rule_state.pop("paused_until", None)
    rule_state.pop("pause_reason", None)
    if rule_state:
        state_rules[rule_id] = rule_state
    elif rule_id in state_rules:
        del state_rules[rule_id]
    _save_alarm3_state(state)
    log.info("Alarm 3 rule %s unpaused", rule_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_dt(raw: object) -> datetime | None:
    """Parse a datetime from a Log Analytics row value or ISO string, normalising to UTC."""
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(raw))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _window_label(minutes: int) -> str:
    """Convert a window duration in minutes to a short human-readable string (e.g. ``"15 min"``)."""
    if minutes < 60:
        return f"{minutes} min"
    hours = minutes / 60
    if hours < 24:
        return f"{hours:.0f} hr{'s' if hours != 1 else ''}"
    days = hours / 24
    return f"{days:.0f} day{'s' if days != 1 else ''}"


# ---------------------------------------------------------------------------
# Log Analytics query
# ---------------------------------------------------------------------------


def get_failure_counts(rules: list[dict]) -> dict[str, int | None]:
    """Query MESSAGE_FAILED count per workflow_id over each rule's window.

    Rules are grouped by window_duration_minutes to minimise round-trips.
    Returns {rule_id: count | None}.
    """
    if not config.AZURE_LOG_ANALYTICS_WORKSPACE_ID or not rules:
        return {r["id"]: None for r in rules}

    by_window: dict[int, list[dict]] = {}
    for rule in rules:
        w = int(rule.get("window_duration_minutes", DEFAULT_WINDOW_MINUTES))
        by_window.setdefault(w, []).append(rule)

    results: dict[str, int | None] = {}

    for window_minutes, window_rules in by_window.items():
        safe_ids = [re.sub(r"[^a-zA-Z0-9_\-]", "", r["workflow_id"]) for r in window_rules]
        ids_kql = ", ".join(f'"{s}"' for s in safe_ids)
        resource_filter = ""
        if config.AZURE_APP_INSIGHTS_RESOURCE_ID:
            resource_filter = f"\n        | where _ResourceId =~ '{config.AZURE_APP_INSIGHTS_RESOURCE_ID}'"

        query = f"""
        AppTraces
        | where TimeGenerated > ago({window_minutes}m){resource_filter}
        | where Message has "Integration Hub Event"
        | extend workflow_id = tostring(parse_json(Properties)["workflow_id"]),
                 event_type  = tostring(parse_json(Properties)["event_type"])
        | where workflow_id in ({ids_kql})
        | where event_type == "MESSAGE_FAILED"
        | summarize Total = count() by workflow_id
        """
        try:
            client = LogsQueryClient(get_azure_credential())
            response = client.query_workspace(
                workspace_id=config.AZURE_LOG_ANALYTICS_WORKSPACE_ID,
                query=query,
                timespan=timedelta(minutes=window_minutes),
            )
            if response.status != LogsQueryStatus.SUCCESS:
                log.warning("alarm3 query partial/failed for window=%dm", window_minutes)
                for r in window_rules:
                    results[r["id"]] = None
                continue

            found: dict[str, int] = {}
            for table in response.tables:
                for row in table.rows:
                    row_dict = dict(zip(table.columns, row))
                    wid = (row_dict.get("workflow_id") or "").strip()
                    val = row_dict.get("Total")
                    if wid:
                        found[wid] = int(val) if val is not None else 0

            for r in window_rules:
                # Missing key = no failures found in window → count is 0
                results[r["id"]] = found.get(r["workflow_id"].strip(), 0)

        except Exception as exc:
            log.error("alarm3 query failed for window=%dm: %s", window_minutes, exc)
            for r in window_rules:
                results[r["id"]] = None

    return results


# ---------------------------------------------------------------------------
# Email notification
# ---------------------------------------------------------------------------


def _send_alarm3_email(
    rule_id: str,
    display_name: str,
    failure_count: int,
    threshold: int,
    window_minutes: int,
    workflow_id: str,
    now: datetime,
    email_alerts_enabled: bool = False,
) -> None:
    """Send an HTML email via Azure Communication Services when Alarm 3 fires."""
    if not email_alerts_enabled:
        return

    window_label = _window_label(window_minutes)
    subject = f"[Integration Hub] Alarm 3 — {display_name} message failures ({failure_count} failed)"
    body = f"""<html><body style="font-family:Arial,sans-serif;color:#333;max-width:600px;">
<h2 style="color:#c0392b;border-bottom:2px solid #c0392b;padding-bottom:8px;">
  &#x26A0; Integration Hub — Alarm 3: Message Processing Failures
</h2>
<p style="color:#555;font-size:14px;">
  The following workflow has recorded MESSAGE_FAILED events above the configured threshold.
</p>
<table cellpadding="8" cellspacing="0"
       style="border-collapse:collapse;font-size:14px;width:100%;
              background:#f9f9f9;border:1px solid #ddd;border-radius:4px;">
  <tr style="background:#fff;">
    <td style="font-weight:bold;width:180px;border-bottom:1px solid #eee;">Rule</td>
    <td style="border-bottom:1px solid #eee;">{display_name}</td>
  </tr>
  <tr>
    <td style="font-weight:bold;border-bottom:1px solid #eee;">Workflow ID</td>
    <td style="border-bottom:1px solid #eee;font-family:monospace;">{workflow_id}</td>
  </tr>
  <tr style="background:#fff;">
    <td style="font-weight:bold;border-bottom:1px solid #eee;">Failures Detected</td>
    <td style="border-bottom:1px solid #eee;color:#c0392b;font-weight:bold;">{failure_count:,}</td>
  </tr>
  <tr>
    <td style="font-weight:bold;border-bottom:1px solid #eee;">Threshold</td>
    <td style="border-bottom:1px solid #eee;">&gt;= {threshold:,}</td>
  </tr>
  <tr style="background:#fff;">
    <td style="font-weight:bold;border-bottom:1px solid #eee;">Lookback Window</td>
    <td style="border-bottom:1px solid #eee;">{window_label}</td>
  </tr>
  <tr>
    <td style="font-weight:bold;">Fired At (UTC)</td>
    <td>{now.strftime("%d %b %Y  %H:%M:%S UTC")}</td>
  </tr>
</table>
<p style="font-size:12px;color:#999;margin-top:24px;">
  NHS Wales Integration Hub — automated alarm notification
</p>
</body></html>"""

    if not send_alert_email(subject, body) and config.ALERT_EMAIL_ENABLED:
        # send_alert_email() already logs a warning (missing config) or error (send
        # failure, e.g. ACS throttling) for real failure cases. When ALERT_EMAIL_ENABLED
        # is False, a False return is expected/intentional, so avoid a noisy log here.
        log.warning("Failed to send alarm 3 email for %s", rule_id)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_alarm3_status() -> list[dict]:
    """Evaluate Alarm 3 for all enabled rules and return their status rows.

    Status values:
        'critical'   – failure count >= threshold, cooldown expired
        'suppressed' – failure count >= threshold, within cooldown
        'healthy'    – failure count below threshold
        'unknown'    – query failed or Log Analytics not configured
    """
    cfg = load_alarm3_config()
    rules_cfg = cfg.get("rules", {})

    all_rules = _all_known_rules(rules_cfg)
    enabled_rules = [r for r in all_rules if rules_cfg.get(r["id"], {}).get("alarm_enabled", False)]

    if not enabled_rules:
        return []

    counts = get_failure_counts(enabled_rules)
    now = datetime.now(timezone.utc)

    state = _load_alarm3_state()
    state_rules = state.setdefault("rules", {})
    state_dirty = False

    results: list[dict] = []

    for rule in enabled_rules:
        rid = rule["id"]
        rule_cfg = rules_cfg.get(rid, {})
        threshold = int(rule_cfg.get("threshold", DEFAULT_THRESHOLD))
        gap = int(rule_cfg.get("alerting_gap_minutes", DEFAULT_ALERTING_GAP))
        count = counts.get(rid)

        # Check for manual pause before any alarm evaluation.
        rule_state = state_rules.get(rid, {})
        paused_until = _parse_dt(rule_state.get("paused_until"))
        if paused_until and paused_until > now:
            pause_remaining = (paused_until - now).total_seconds() / 60
            results.append(
                _build_row(
                    rid,
                    rule,
                    rule_cfg,
                    count=count,
                    status="paused",
                    cooldown_remaining=None,
                    now=now,
                    pause_remaining=pause_remaining,
                    pause_reason=rule_state.get("pause_reason", ""),
                    paused_until=paused_until,
                )
            )
            continue
        # Clear stale pause state if the pause window has elapsed.
        if paused_until and paused_until <= now:
            rule_state.pop("paused_until", None)
            rule_state.pop("pause_reason", None)
            if rule_state:
                state_rules[rid] = rule_state
            elif rid in state_rules:
                del state_rules[rid]
            state_dirty = True

        if count is None:
            results.append(
                _build_row(rid, rule, rule_cfg, count=None, status="unknown", cooldown_remaining=None, now=now)
            )
            continue

        in_alarm = count >= threshold

        if not in_alarm:
            if rid in state_rules:
                del state_rules[rid]
                state_dirty = True
            results.append(
                _build_row(rid, rule, rule_cfg, count=count, status="healthy", cooldown_remaining=None, now=now)
            )
            continue

        # --- In alarm condition ---
        last_alarm_at = _parse_dt(state_rules.get(rid, {}).get("last_alarm_at"))

        if last_alarm_at is None:
            status = "critical"
            state_rules.setdefault(rid, {})["last_alarm_at"] = now.isoformat()
            state_dirty = True
            cooldown_remaining = None
            _send_alarm3_email(
                rid,
                rule_cfg.get("display_name") or rule.get("display_name", rid),
                count,
                threshold,
                int(rule_cfg.get("window_duration_minutes", DEFAULT_WINDOW_MINUTES)),
                rule_cfg.get("workflow_id", rule.get("workflow_id", "")),
                now,
                email_alerts_enabled=rule_cfg.get("email_alerts_enabled", False),
            )
        else:
            mins_since = (now - last_alarm_at).total_seconds() / 60
            if mins_since >= gap:
                status = "critical"
                state_rules[rid]["last_alarm_at"] = now.isoformat()
                state_dirty = True
                cooldown_remaining = None
                _send_alarm3_email(
                    rid,
                    rule_cfg.get("display_name") or rule.get("display_name", rid),
                    count,
                    threshold,
                    int(rule_cfg.get("window_duration_minutes", DEFAULT_WINDOW_MINUTES)),
                    rule_cfg.get("workflow_id", rule.get("workflow_id", "")),
                    now,
                    email_alerts_enabled=rule_cfg.get("email_alerts_enabled", False),
                )
            else:
                status = "suppressed"
                cooldown_remaining = gap - mins_since

        results.append(
            _build_row(rid, rule, rule_cfg, count=count, status=status, cooldown_remaining=cooldown_remaining, now=now)
        )

    if state_dirty:
        _save_alarm3_state({"rules": state_rules})

    _order = {"paused": 0, "critical": 1, "suppressed": 2, "unknown": 3, "healthy": 4}
    results.sort(key=lambda r: _order.get(r["status"], 9))
    return results


def _build_row(
    rid: str,
    rule_seed: dict,
    rule_cfg: dict,
    count: int | None,
    status: str,
    cooldown_remaining: float | None,
    now: datetime,
    pause_remaining: float | None = None,
    pause_reason: str = "",
    paused_until: datetime | None = None,
) -> dict:
    """Build the status-row dict for a single Alarm 3 rule."""
    window = int(rule_cfg.get("window_duration_minutes", DEFAULT_WINDOW_MINUTES))
    return {
        "id": rid,
        "display_name": rule_cfg.get("display_name") or rule_seed.get("display_name", rid),
        "workflow_id": rule_cfg.get("workflow_id", rule_seed.get("workflow_id", "")),
        "window_duration_minutes": window,
        "window_label": _window_label(window),
        "threshold": int(rule_cfg.get("threshold", DEFAULT_THRESHOLD)),
        "alerting_gap_minutes": int(rule_cfg.get("alerting_gap_minutes", DEFAULT_ALERTING_GAP)),
        "failure_count": count,
        "failure_display": f"{count:,}" if count is not None else "—",
        "status": status,
        "cooldown_remaining": round(cooldown_remaining, 0) if cooldown_remaining is not None else None,
        "pause_remaining": round(pause_remaining, 0) if pause_remaining is not None else None,
        "pause_reason": pause_reason,
        "paused_until": paused_until.strftime("%d %b %Y  %H:%M UTC") if paused_until else None,
    }


def _all_known_rules(rules_cfg: dict) -> list[dict]:
    """Merge the seed list with any extra rules stored in config, skipping deleted ones."""
    seen: set[str] = set()
    merged: list[dict] = []
    for r in KNOWN_RULES:
        seen.add(r["id"])
        if not rules_cfg.get(r["id"], {}).get("deleted", False):
            merged.append(r)
    for rid, rule_data in rules_cfg.items():
        if rid not in seen and not rule_data.get("deleted", False):
            merged.append(
                {
                    "id": rid,
                    "display_name": rule_data.get("display_name", rid),
                    "workflow_id": rule_data.get("workflow_id", ""),
                }
            )
    return merged


def generate_rule_id(workflow_id: str, existing_ids: set[str]) -> str:
    """Generate a unique kebab-case rule ID from workflow_id."""
    base = re.sub(r"[^a-z0-9]+", "-", workflow_id.lower()).strip("-") + "-failures"
    rid = base
    i = 2
    while rid in existing_ids:
        rid = f"{base}-{i}"
        i += 1
    return rid


def get_alarm3_config_page_data() -> list[dict]:
    """Return all known rules with their current settings for the config form."""
    cfg = load_alarm3_config()
    rules_cfg = cfg.get("rules", {})
    return [
        {
            "id": r["id"],
            "display_name": rules_cfg.get(r["id"], {}).get("display_name") or r.get("display_name", r["id"]),
            "alarm_enabled": rules_cfg.get(r["id"], {}).get("alarm_enabled", False),
            "workflow_id": rules_cfg.get(r["id"], {}).get("workflow_id", r.get("workflow_id", "")),
            "window_duration_minutes": int(
                rules_cfg.get(r["id"], {}).get("window_duration_minutes", DEFAULT_WINDOW_MINUTES)
            ),
            "threshold": int(rules_cfg.get(r["id"], {}).get("threshold", DEFAULT_THRESHOLD)),
            "alerting_gap_minutes": int(rules_cfg.get(r["id"], {}).get("alerting_gap_minutes", DEFAULT_ALERTING_GAP)),
            "email_alerts_enabled": rules_cfg.get(r["id"], {}).get("email_alerts_enabled", False),
            "email_ooh_enabled": (
                rules_cfg.get(r["id"], {}).get("email_ooh_enabled", False)
                and rules_cfg.get(r["id"], {}).get("email_alerts_enabled", False)
            ),
        }
        for r in _all_known_rules(rules_cfg)
    ]
