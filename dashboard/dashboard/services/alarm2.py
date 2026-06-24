"""Alarm 2 service — outgoing message inactivity monitoring.

Config is persisted to ``alarm2_config.json`` in the dashboard root directory.
State (last alarm fired time per rule) is persisted to ``alarm2_state.json``.

Each rule monitors the most recent ``messages_sent`` metric for a specific
workflow_id and has the following settings:
  alarm_enabled              – bool, whether Alarm 2 is active for this rule
  display_name               – human-readable label
  workflow_id                – Properties["workflow_id"] filter value (e.g. "phw-to-mpi")
  day_threshold_minutes      – minutes of inactivity during Day to trip the alarm
  evening_threshold_minutes  – minutes of inactivity during Evening to trip the alarm
  weekend_threshold_minutes  – minutes of inactivity during Weekend to trip the alarm
  alerting_gap_minutes       – cooldown before the alarm re-fires
  email_alerts_enabled       – bool, whether to send email on alarm

Status values returned per rule:
  'critical'   – inactivity exceeds threshold, cooldown has expired
  'suppressed' – inactivity exceeds threshold but within the re-alarm cooldown
  'healthy'    – last message sent within the inactivity threshold
  'unknown'    – query failed or no Log Analytics workspace configured
"""

from __future__ import annotations

import json
import logging
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from azure.monitor.query import LogsQueryClient, LogsQueryStatus

from dashboard import config
from dashboard.services.alarm_time_utils import PERIOD_SHORT_LABELS, get_current_period
from dashboard.services.credentials import get_azure_credential

log = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent.parent.parent / "alarm2_config.json"
STATE_PATH = Path(__file__).parent.parent.parent / "alarm2_state.json"

DEFAULT_DAY_THRESHOLD = 60
DEFAULT_EVENING_THRESHOLD = 120
DEFAULT_WEEKEND_THRESHOLD = 240
DEFAULT_ALERTING_GAP = 60

# Seed list of known rules — always present even if not yet enabled.
KNOWN_RULES: list[dict] = [
    {
        "id": "phw-to-mpi-outgoing",
        "display_name": "PHW → MPI Outgoing",
        "workflow_id": "phw-to-mpi",
    },
]


# ---------------------------------------------------------------------------
# Config / state persistence
# ---------------------------------------------------------------------------


def load_alarm2_config() -> dict:
    """Load Alarm 2 config from JSON. Returns empty config on missing/corrupt file."""
    if not CONFIG_PATH.exists():
        return {"rules": {}}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Failed to load alarm2 config: %s", exc)
        return {"rules": {}}


def save_alarm2_config(cfg: dict) -> None:
    """Persist Alarm 2 config to JSON."""
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, default=str), encoding="utf-8")


def _load_alarm2_state() -> dict:
    """Load per-rule Alarm 2 state (last_alarm_at timestamps) from JSON. Returns empty state on missing/corrupt file."""
    if not STATE_PATH.exists():
        return {"rules": {}}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Failed to load alarm2 state: %s", exc)
        return {"rules": {}}


def _save_alarm2_state(state: dict) -> None:
    """Persist per-rule Alarm 2 state to JSON, logging errors without raising."""
    try:
        STATE_PATH.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    except OSError as exc:
        log.error("Failed to save alarm2 state: %s", exc)


# ---------------------------------------------------------------------------
# Pause / unpause helpers
# ---------------------------------------------------------------------------


def pause_alarm2_rule(rule_id: str, duration_minutes: int, reason: str = "") -> None:
    """Pause a specific Alarm 2 rule for ``duration_minutes``.

    Writes ``paused_until`` (ISO timestamp) and ``pause_reason`` into the rule's
    state entry.  The alarm evaluator will skip the rule and return ``status='paused'``
    until that time has elapsed.
    """
    state = _load_alarm2_state()
    state_rules = state.setdefault("rules", {})
    now = datetime.now(timezone.utc)
    paused_until = now + timedelta(minutes=duration_minutes)
    state_rules.setdefault(rule_id, {}).update(
        {
            "paused_until": paused_until.isoformat(),
            "pause_reason": reason.strip(),
        }
    )
    _save_alarm2_state(state)
    log.info(
        "Alarm 2 rule %s paused for %d minutes (until %s). Reason: %s",
        rule_id,
        duration_minutes,
        paused_until.isoformat(),
        reason or "(none)",
    )


def unpause_alarm2_rule(rule_id: str) -> None:
    """Remove a manual pause from a specific Alarm 2 rule, restoring normal evaluation."""
    state = _load_alarm2_state()
    state_rules = state.get("rules", {})
    rule_state = state_rules.get(rule_id, {})
    rule_state.pop("paused_until", None)
    rule_state.pop("pause_reason", None)
    if rule_state:
        state_rules[rule_id] = rule_state
    elif rule_id in state_rules:
        del state_rules[rule_id]
    _save_alarm2_state(state)
    log.info("Alarm 2 rule %s unpaused", rule_id)


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


def _format_duration(minutes: float) -> str:
    """Format a duration in minutes as a human-readable string (e.g. ``"2.5 hours"``)."""
    if minutes < 1:
        return "< 1 minute"
    if minutes < 60:
        m = int(minutes)
        return f"{m} minute{'s' if m != 1 else ''}"
    hours = minutes / 60
    if hours < 24:
        return f"{hours:.1f} hour{'s' if hours != 1.0 else ''}"
    days = hours / 24
    return f"{days:.1f} day{'s' if days != 1.0 else ''}"


def _applicable_threshold(rule_cfg: dict, now: datetime) -> int:
    """Return the inactivity trip threshold in minutes for the current time period.

    Falls back to the legacy single ``threshold`` field for configs created
    before per-period thresholds were introduced.
    """
    legacy = rule_cfg.get("threshold", None)
    period = get_current_period(now)
    if period == "weekend":
        return int(
            rule_cfg.get("weekend_threshold_minutes", legacy if legacy is not None else DEFAULT_WEEKEND_THRESHOLD)
        )
    if period == "day":
        return int(rule_cfg.get("day_threshold_minutes", legacy if legacy is not None else DEFAULT_DAY_THRESHOLD))
    return int(rule_cfg.get("evening_threshold_minutes", legacy if legacy is not None else DEFAULT_EVENING_THRESHOLD))


# ---------------------------------------------------------------------------
# Log Analytics query
# ---------------------------------------------------------------------------


def get_last_sent_times_by_workflow(workflow_ids: list[str], lookback_days: int = 3) -> dict[str, datetime | None]:
    """Query Log Analytics for the most recent messages_sent metric per workflow_id.

    Args:
        workflow_ids:   List of workflow IDs to query.
        lookback_days:  How far back to search. Should be at least
                        ceil(max_threshold_minutes / 1440) so that a workflow
                        inactive for longer than its threshold returns a real
                        last-seen time rather than no row (which would produce
                        'unknown' instead of 'critical').
    """
    if not config.AZURE_LOG_ANALYTICS_WORKSPACE_ID or not workflow_ids:
        return {wid: None for wid in workflow_ids}

    safe_ids = [re.sub(r"[^a-zA-Z0-9\-_]", "", wid) for wid in workflow_ids if wid]
    if not safe_ids:
        return {wid: None for wid in workflow_ids}

    ids_kql = ", ".join(f'"{w}"' for w in safe_ids)
    query = f"""
    AppMetrics
    | where TimeGenerated > ago({lookback_days}d)
    | where Name == "messages_sent"
    | extend workflow_id = tostring(Properties["workflow_id"])
    | where workflow_id in ({ids_kql})
    | summarize last_message = max(TimeGenerated) by workflow_id
    """
    try:
        client = LogsQueryClient(get_azure_credential())
        response = client.query_workspace(
            workspace_id=config.AZURE_LOG_ANALYTICS_WORKSPACE_ID,
            query=query,
            timespan=timedelta(days=lookback_days),
        )
        if response.status != LogsQueryStatus.SUCCESS:
            log.warning("get_last_sent_times_by_workflow: partial/failed query")
            return {wid: None for wid in workflow_ids}

        found: dict[str, datetime | None] = {}
        for table in response.tables:
            for row in table.rows:
                row_dict = dict(zip(table.columns, row))
                wid = (row_dict.get("workflow_id") or "").strip()
                ts = _parse_dt(row_dict.get("last_message"))
                if wid:
                    found[wid] = ts

        return {wid: found.get(wid) for wid in workflow_ids}

    except Exception as exc:
        log.error("Failed to fetch last sent times: %s", exc)
        return {wid: None for wid in workflow_ids}


# ---------------------------------------------------------------------------
# Email notification
# ---------------------------------------------------------------------------


def _send_alarm2_email(
    rule_id: str,
    workflow_id: str,
    display_name: str,
    minutes_since: float,
    period_threshold: int,
    last_msg: datetime | None,
    now: datetime,
    email_alerts_enabled: bool = False,
) -> None:
    """Send an HTML email via Azure Communication Services when Alarm 2 fires."""
    if not config.ALERT_EMAIL_ENABLED:
        return
    if not email_alerts_enabled:
        return
    if not config.ACS_CONNECTION_STRING or not config.ALERT_EMAIL_TO:
        log.warning("Alarm 2 email enabled but ACS/ALERT_EMAIL_TO not set — skipping")
        return

    from dashboard.services.alarm_time_utils import PERIOD_LABELS  # noqa: PLC0415

    period = get_current_period(now)
    period_label = PERIOD_LABELS.get(period, period.title())
    last_msg_str = last_msg.strftime("%d %b %Y  %H:%M:%S UTC") if last_msg else "Never / unknown"
    duration_str = _format_duration(minutes_since)

    subject = f"[Integration Hub] Alarm 2 — {display_name} outgoing inactivity ({duration_str})"
    body = f"""<html><body style="font-family:Arial,sans-serif;color:#333;max-width:600px;">
<h2 style="color:#c0392b;border-bottom:2px solid #c0392b;padding-bottom:8px;">
  &#x26A0; Integration Hub — Alarm 2: Outgoing Message Inactivity
</h2>
<p style="color:#555;font-size:14px;">
  The following workflow has sent no messages for longer than its configured threshold.
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
    <td style="font-weight:bold;border-bottom:1px solid #eee;">Last Sent (UTC)</td>
    <td style="border-bottom:1px solid #eee;">{last_msg_str}</td>
  </tr>
  <tr>
    <td style="font-weight:bold;border-bottom:1px solid #eee;">Inactive For</td>
    <td style="border-bottom:1px solid #eee;color:#c0392b;font-weight:bold;">{duration_str}</td>
  </tr>
  <tr style="background:#fff;">
    <td style="font-weight:bold;border-bottom:1px solid #eee;">Period / Threshold</td>
    <td style="border-bottom:1px solid #eee;">{period_label} — {period_threshold} min</td>
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

    try:
        from azure.communication.email import EmailClient  # noqa: PLC0415

        client = EmailClient.from_connection_string(config.ACS_CONNECTION_STRING)
        message = {
            "senderAddress": config.ALERT_EMAIL_FROM,
            "recipients": {"to": [{"address": config.ALERT_EMAIL_TO}]},
            "content": {"subject": subject, "html": body},
        }
        poller = client.begin_send(message)
        poller.result()
        log.info("Alarm 2 email sent for %s to %s", rule_id, config.ALERT_EMAIL_TO)
    except Exception as exc:
        log.error("Failed to send alarm 2 email for %s: %s", rule_id, exc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_alarm2_status() -> list[dict]:
    """Evaluate Alarm 2 for all enabled rules and return their status rows.

    Status values:
        'critical'   – inactivity exceeds threshold, cooldown expired
        'suppressed' – inactivity exceeds threshold, within cooldown
        'healthy'    – last message sent within the inactivity threshold
        'unknown'    – query failed or Log Analytics not configured
    """
    cfg = load_alarm2_config()
    rules_cfg = cfg.get("rules", {})

    all_rules = _all_known_rules(rules_cfg)
    enabled_rules = [r for r in all_rules if rules_cfg.get(r["id"], {}).get("alarm_enabled", False)]

    if not enabled_rules:
        return []

    workflow_ids = list(
        dict.fromkeys(
            rules_cfg.get(r["id"], {}).get("workflow_id", r.get("workflow_id", "")).strip()
            for r in enabled_rules
            if rules_cfg.get(r["id"], {}).get("workflow_id", r.get("workflow_id", "")).strip()
        )
    )

    # Derive lookback from the largest configured threshold across all enabled rules
    # so that a workflow inactive longer than its threshold returns a real timestamp
    # (not a missing row, which would yield 'unknown' instead of 'critical').
    max_threshold_minutes = max(
        (
            max(
                int(rules_cfg.get(r["id"], {}).get("day_threshold_minutes", DEFAULT_DAY_THRESHOLD)),
                int(rules_cfg.get(r["id"], {}).get("evening_threshold_minutes", DEFAULT_EVENING_THRESHOLD)),
                int(rules_cfg.get(r["id"], {}).get("weekend_threshold_minutes", DEFAULT_WEEKEND_THRESHOLD)),
            )
            for r in enabled_rules
        ),
        default=DEFAULT_WEEKEND_THRESHOLD,
    )
    # Convert to days, add 1-day buffer, cap at 30 days (Log Analytics typical retention).
    lookback_days = min(math.ceil(max_threshold_minutes / 1440) + 1, 30)

    last_times = get_last_sent_times_by_workflow(workflow_ids, lookback_days=lookback_days)
    now = datetime.now(timezone.utc)

    state = _load_alarm2_state()
    state_rules = state.setdefault("rules", {})
    state_dirty = False

    results: list[dict] = []

    for rule in enabled_rules:
        rid = rule["id"]
        rule_cfg = rules_cfg.get(rid, {})
        workflow_id = rule_cfg.get("workflow_id", rule.get("workflow_id", "")).strip()
        period_threshold = _applicable_threshold(rule_cfg, now)
        gap = int(rule_cfg.get("alerting_gap_minutes", DEFAULT_ALERTING_GAP))
        last_msg = last_times.get(workflow_id) if workflow_id else None

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
                    last_msg=last_msg,
                    status="paused",
                    minutes_since=(now - last_msg).total_seconds() / 60 if last_msg else None,
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

        if last_msg is None:
            results.append(
                _build_row(
                    rid,
                    rule,
                    rule_cfg,
                    last_msg=None,
                    status="unknown",
                    minutes_since=None,
                    cooldown_remaining=None,
                    now=now,
                )
            )
            continue

        minutes_since = (now - last_msg).total_seconds() / 60
        in_alarm = minutes_since > period_threshold

        if not in_alarm:
            if rid in state_rules:
                del state_rules[rid]
                state_dirty = True
            results.append(
                _build_row(
                    rid,
                    rule,
                    rule_cfg,
                    last_msg=last_msg,
                    status="healthy",
                    minutes_since=minutes_since,
                    cooldown_remaining=None,
                    now=now,
                )
            )
            continue

        # --- In alarm condition ---
        display_name = rule_cfg.get("display_name") or rule.get("display_name", rid)
        last_alarm_at = _parse_dt(state_rules.get(rid, {}).get("last_alarm_at"))

        if last_alarm_at is None:
            status = "critical"
            state_rules.setdefault(rid, {})["last_alarm_at"] = now.isoformat()
            state_dirty = True
            cooldown_remaining = None
            _send_alarm2_email(
                rid,
                workflow_id,
                display_name,
                minutes_since,
                period_threshold,
                last_msg,
                now,
                email_alerts_enabled=rule_cfg.get("email_alerts_enabled", False),
            )
        else:
            mins_since_alarm = (now - last_alarm_at).total_seconds() / 60
            if mins_since_alarm >= gap:
                status = "critical"
                state_rules[rid]["last_alarm_at"] = now.isoformat()
                state_dirty = True
                cooldown_remaining = None
                _send_alarm2_email(
                    rid,
                    workflow_id,
                    display_name,
                    minutes_since,
                    period_threshold,
                    last_msg,
                    now,
                    email_alerts_enabled=rule_cfg.get("email_alerts_enabled", False),
                )
            else:
                status = "suppressed"
                cooldown_remaining = gap - mins_since_alarm

        results.append(
            _build_row(
                rid,
                rule,
                rule_cfg,
                last_msg=last_msg,
                status=status,
                minutes_since=minutes_since,
                cooldown_remaining=cooldown_remaining,
                now=now,
            )
        )

    if state_dirty:
        _save_alarm2_state({"rules": state_rules})

    _order = {"paused": 0, "critical": 1, "suppressed": 2, "unknown": 3, "healthy": 4}
    results.sort(key=lambda r: _order.get(r["status"], 9))
    return results


def _build_row(
    rid: str,
    rule_seed: dict,
    rule_cfg: dict,
    last_msg: datetime | None,
    status: str,
    minutes_since: float | None,
    cooldown_remaining: float | None,
    now: datetime,
    pause_remaining: float | None = None,
    pause_reason: str = "",
    paused_until: datetime | None = None,
) -> dict:
    """Build the status-row dict for a single Alarm 2 rule."""
    period = get_current_period(now)
    period_threshold = _applicable_threshold(rule_cfg, now)
    workflow_id = rule_cfg.get("workflow_id", rule_seed.get("workflow_id", "")).strip()
    return {
        "id": rid,
        "display_name": rule_cfg.get("display_name") or rule_seed.get("display_name", rid),
        "workflow_id": workflow_id,
        "day_threshold_minutes": int(
            rule_cfg.get("day_threshold_minutes", rule_cfg.get("threshold", DEFAULT_DAY_THRESHOLD))
        ),
        "evening_threshold_minutes": int(
            rule_cfg.get("evening_threshold_minutes", rule_cfg.get("threshold", DEFAULT_EVENING_THRESHOLD))
        ),
        "weekend_threshold_minutes": int(
            rule_cfg.get("weekend_threshold_minutes", rule_cfg.get("threshold", DEFAULT_WEEKEND_THRESHOLD))
        ),
        "alerting_gap_minutes": int(rule_cfg.get("alerting_gap_minutes", DEFAULT_ALERTING_GAP)),
        "current_period": period,
        "period_threshold_minutes": period_threshold,
        "period_short_label": PERIOD_SHORT_LABELS.get(period, period.title()),
        "last_message": last_msg.isoformat() if last_msg else None,
        "last_message_display": (last_msg.strftime("%d %b %Y  %H:%M:%S UTC") if last_msg else "Never / unknown"),
        "status": status,
        "minutes_since": round(minutes_since, 1) if minutes_since is not None else None,
        "duration_label": _format_duration(minutes_since) if minutes_since is not None else "No data",
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
    for rid, rcfg in rules_cfg.items():
        if rid not in seen and not rcfg.get("deleted", False):
            merged.append(
                {"id": rid, "display_name": rcfg.get("display_name", rid), "workflow_id": rcfg.get("workflow_id", "")}
            )
    return merged


def generate_rule_id(workflow_id: str, existing_ids: set[str]) -> str:
    """Generate a unique kebab-case rule ID from workflow_id."""
    base = re.sub(r"[^a-z0-9]+", "-", workflow_id.lower()).strip("-") + "-outgoing"
    rid = base
    i = 2
    while rid in existing_ids:
        rid = f"{base}-{i}"
        i += 1
    return rid


def get_alarm2_config_page_data() -> list[dict]:
    """Return all known rules with their current settings for the config form."""
    cfg = load_alarm2_config()
    rules_cfg = cfg.get("rules", {})
    result = []
    for r in _all_known_rules(rules_cfg):
        rcfg = rules_cfg.get(r["id"], {})
        result.append(
            {
                "id": r["id"],
                "display_name": rcfg.get("display_name") or r.get("display_name", r["id"]),
                "alarm_enabled": rcfg.get("alarm_enabled", False),
                "workflow_id": rcfg.get("workflow_id", r.get("workflow_id", "")),
                "day_threshold_minutes": int(
                    rcfg.get("day_threshold_minutes", rcfg.get("threshold", DEFAULT_DAY_THRESHOLD))
                ),
                "evening_threshold_minutes": int(
                    rcfg.get("evening_threshold_minutes", rcfg.get("threshold", DEFAULT_EVENING_THRESHOLD))
                ),
                "weekend_threshold_minutes": int(
                    rcfg.get("weekend_threshold_minutes", rcfg.get("threshold", DEFAULT_WEEKEND_THRESHOLD))
                ),
                "alerting_gap_minutes": int(rcfg.get("alerting_gap_minutes", DEFAULT_ALERTING_GAP)),
                "email_alerts_enabled": rcfg.get("email_alerts_enabled", False),
                "email_ooh_enabled": rcfg.get("email_ooh_enabled", False),
            }
        )
    return result
