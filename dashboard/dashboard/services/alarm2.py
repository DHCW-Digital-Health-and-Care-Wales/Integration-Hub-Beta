"""Alarm 2 service — outgoing message volume monitoring.

Config is persisted to ``alarm2_config.json`` in the dashboard root directory.
State (last alarm fired time per rule) is persisted to ``alarm2_state.json``.

Each rule monitors MESSAGE_SENT events for a specific workflow_id and has
the following settings:
  alarm_enabled            – bool, whether Alarm 2 is active for this rule
  display_name             – human-readable label
  workflow_id              – Properties["workflow_id"] filter value (e.g. "phw-to-mpi")
  window_duration_minutes  – lookback window for the messages_sent query
  threshold                – fire when sum(messages_sent) <= this value
  alerting_gap_minutes     – cooldown before the alarm re-fires
  email_alerts_enabled     – bool, whether to send email on alarm

Status values returned per rule:
  'critical'   – count at/below threshold, cooldown has expired
  'suppressed' – count at/below threshold but within the re-alarm cooldown
  'healthy'    – count above threshold
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

log = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent.parent.parent / "alarm2_config.json"
STATE_PATH  = Path(__file__).parent.parent.parent / "alarm2_state.json"

DEFAULT_WINDOW_MINUTES = 2880   # 2 days
DEFAULT_THRESHOLD      = 0
DEFAULT_ALERTING_GAP   = 60

# Seed list of known rules — always present even if not yet enabled.
KNOWN_RULES: list[dict] = [
    {
        "id":           "phw-to-mpi-outgoing",
        "display_name": "PHW → MPI Outgoing",
        "workflow_id":  "phw-to-mpi",
    },
]


# ---------------------------------------------------------------------------
# Config / state persistence
# ---------------------------------------------------------------------------

def load_alarm2_config() -> dict:
    if not CONFIG_PATH.exists():
        return {"rules": {}}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Failed to load alarm2 config: %s", exc)
        return {"rules": {}}


def save_alarm2_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, default=str), encoding="utf-8")


def _load_alarm2_state() -> dict:
    if not STATE_PATH.exists():
        return {"rules": {}}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Failed to load alarm2 state: %s", exc)
        return {"rules": {}}


def _save_alarm2_state(state: dict) -> None:
    try:
        STATE_PATH.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    except OSError as exc:
        log.error("Failed to save alarm2 state: %s", exc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_dt(raw: object) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(raw))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _format_count(total: int | None) -> str:
    if total is None:
        return "—"
    return f"{total:,}"


# ---------------------------------------------------------------------------
# Log Analytics query
# ---------------------------------------------------------------------------

def get_messages_totals(rules: list[dict]) -> dict[str, int | None]:
    """Query sum(messages_sent) for each rule over its configured window.

    Rules are grouped by window_duration_minutes so we only issue one query
    per unique window size.  Returns {rule_id: total | None}.
    """
    if not config.AZURE_LOG_ANALYTICS_WORKSPACE_ID or not rules:
        return {r["id"]: None for r in rules}

    # Group rules by window size to minimise round-trips.
    by_window: dict[int, list[dict]] = {}
    for rule in rules:
        w = int(rule.get("window_duration_minutes", DEFAULT_WINDOW_MINUTES))
        by_window.setdefault(w, []).append(rule)

    results: dict[str, int | None] = {}

    for window_minutes, window_rules in by_window.items():
        safe_ids = [
            re.sub(r"[^a-zA-Z0-9_\-]", "", r["workflow_id"])
            for r in window_rules
        ]
        ids_kql = ", ".join(f'"{s}"' for s in safe_ids)
        query = f"""
        AppMetrics
        | where TimeGenerated > ago({window_minutes}m)
        | where Name == "messages_sent"
        | extend workflow_id = tostring(Properties["workflow_id"])
        | where workflow_id in ({ids_kql})
        | summarize Total = sum(Sum) by workflow_id
        """
        try:
            client = LogsQueryClient(get_azure_credential())
            response = client.query_workspace(
                workspace_id=config.AZURE_LOG_ANALYTICS_WORKSPACE_ID,
                query=query,
                timespan=timedelta(minutes=window_minutes),
            )
            if response.status != LogsQueryStatus.SUCCESS:
                log.warning("alarm2 query partial/failed for window=%dm", window_minutes)
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
                # Missing key = no messages found in window → treat as 0.
                results[r["id"]] = found.get(r["workflow_id"].strip(), 0)

        except Exception as exc:
            log.error("alarm2 query failed for window=%dm: %s", window_minutes, exc)
            for r in window_rules:
                results[r["id"]] = None

    return results


# ---------------------------------------------------------------------------
# Email notification
# ---------------------------------------------------------------------------

def _send_alarm2_email(
    rule_id: str,
    display_name: str,
    messages_total: int,
    threshold: int,
    window_minutes: int,
    workflow_id: str,
    now: datetime,
    email_alerts_enabled: bool = False,
) -> None:
    if not config.ALERT_EMAIL_ENABLED:
        return
    if not email_alerts_enabled:
        return
    if not config.ACS_CONNECTION_STRING or not config.ALERT_EMAIL_TO:
        log.warning("Alarm 2 email enabled but ACS/ALERT_EMAIL_TO not set — skipping")
        return

    window_label = f"{window_minutes // 60} hours" if window_minutes >= 60 else f"{window_minutes} minutes"
    subject = f"[Integration Hub] Alarm 2 — {display_name} low message volume ({messages_total} messages)"
    body = f"""<html><body style="font-family:Arial,sans-serif;color:#333;max-width:600px;">
<h2 style="color:#c0392b;border-bottom:2px solid #c0392b;padding-bottom:8px;">
  &#x26A0; Integration Hub — Alarm 2: Low Outgoing Message Volume
</h2>
<p style="color:#555;font-size:14px;">
  The following flow has sent fewer messages than the configured threshold.
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
    <td style="font-weight:bold;border-bottom:1px solid #eee;">Messages Sent</td>
    <td style="border-bottom:1px solid #eee;color:#c0392b;font-weight:bold;">{messages_total:,}</td>
  </tr>
  <tr>
    <td style="font-weight:bold;border-bottom:1px solid #eee;">Threshold</td>
    <td style="border-bottom:1px solid #eee;">&lt;= {threshold:,}</td>
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
        'critical'   – message count at/below threshold, cooldown expired
        'suppressed' – message count at/below threshold, within cooldown
        'healthy'    – message count above threshold
        'unknown'    – query failed or Log Analytics not configured
    """
    cfg = load_alarm2_config()
    rules_cfg = cfg.get("rules", {})

    all_rules = _all_known_rules(rules_cfg)
    enabled_rules = [r for r in all_rules if rules_cfg.get(r["id"], {}).get("alarm_enabled", False)]

    if not enabled_rules:
        return []

    totals = get_messages_totals(enabled_rules)
    now    = datetime.now(timezone.utc)

    state = _load_alarm2_state()
    state_rules = state.setdefault("rules", {})
    state_dirty = False

    results: list[dict] = []

    for rule in enabled_rules:
        rid        = rule["id"]
        rule_cfg   = rules_cfg.get(rid, {})
        threshold  = int(rule_cfg.get("threshold", DEFAULT_THRESHOLD))
        gap        = int(rule_cfg.get("alerting_gap_minutes", DEFAULT_ALERTING_GAP))
        total      = totals.get(rid)

        if total is None:
            results.append(_build_row(rid, rule, rule_cfg, total=None, status="unknown",
                                      cooldown_remaining=None, now=now))
            continue

        in_alarm = total <= threshold

        if not in_alarm:
            if rid in state_rules:
                del state_rules[rid]
                state_dirty = True
            results.append(_build_row(rid, rule, rule_cfg, total=total, status="healthy",
                                      cooldown_remaining=None, now=now))
            continue

        # --- In alarm condition ---
        last_alarm_at = _parse_dt(state_rules.get(rid, {}).get("last_alarm_at"))

        if last_alarm_at is None:
            status = "critical"
            state_rules.setdefault(rid, {})["last_alarm_at"] = now.isoformat()
            state_dirty = True
            cooldown_remaining = None
            _send_alarm2_email(
                rid,
                rule_cfg.get("display_name") or rule.get("display_name", rid),
                total, threshold,
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
                _send_alarm2_email(
                    rid,
                    rule_cfg.get("display_name") or rule.get("display_name", rid),
                    total, threshold,
                    int(rule_cfg.get("window_duration_minutes", DEFAULT_WINDOW_MINUTES)),
                    rule_cfg.get("workflow_id", rule.get("workflow_id", "")),
                    now,
                    email_alerts_enabled=rule_cfg.get("email_alerts_enabled", False),
                )
            else:
                status = "suppressed"
                cooldown_remaining = gap - mins_since

        results.append(_build_row(rid, rule, rule_cfg, total=total, status=status,
                                  cooldown_remaining=cooldown_remaining, now=now))

    if state_dirty:
        _save_alarm2_state({"rules": state_rules})

    _order = {"critical": 0, "suppressed": 1, "unknown": 2, "healthy": 3}
    results.sort(key=lambda r: _order.get(r["status"], 9))
    return results


def _build_row(
    rid: str,
    rule_seed: dict,
    rule_cfg: dict,
    total: int | None,
    status: str,
    cooldown_remaining: float | None,
    now: datetime,
) -> dict:
    window = int(rule_cfg.get("window_duration_minutes", DEFAULT_WINDOW_MINUTES))
    return {
        "id":                      rid,
        "display_name":            rule_cfg.get("display_name") or rule_seed.get("display_name", rid),
        "workflow_id":             rule_cfg.get("workflow_id",  rule_seed.get("workflow_id",  "")),
        "window_duration_minutes": window,
        "window_label":            _window_label(window),
        "threshold":               int(rule_cfg.get("threshold",          DEFAULT_THRESHOLD)),
        "alerting_gap_minutes":    int(rule_cfg.get("alerting_gap_minutes", DEFAULT_ALERTING_GAP)),
        "messages_total":          total,
        "messages_display":        _format_count(total),
        "status":                  status,
        "cooldown_remaining":      round(cooldown_remaining, 0) if cooldown_remaining is not None else None,
    }


def _window_label(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} min"
    hours = minutes / 60
    if hours < 24:
        return f"{hours:.0f} hr{'s' if hours != 1 else ''}"
    days = hours / 24
    return f"{days:.0f} day{'s' if days != 1 else ''}"


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
            merged.append({"id": rid,
                           "display_name": rcfg.get("display_name", rid),
                           "workflow_id":  rcfg.get("workflow_id", "")})
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
    return [
        {
            "id":                      r["id"],
            "display_name":            rules_cfg.get(r["id"], {}).get("display_name")
                                       or r.get("display_name", r["id"]),
            "alarm_enabled":           rules_cfg.get(r["id"], {}).get("alarm_enabled", False),
            "workflow_id":             rules_cfg.get(r["id"], {}).get("workflow_id",
                                                                       r.get("workflow_id", "")),
            "window_duration_minutes": int(rules_cfg.get(r["id"], {}).get(
                                           "window_duration_minutes", DEFAULT_WINDOW_MINUTES)),
            "threshold":               int(rules_cfg.get(r["id"], {}).get(
                                           "threshold", DEFAULT_THRESHOLD)),
            "alerting_gap_minutes":    int(rules_cfg.get(r["id"], {}).get(
                                           "alerting_gap_minutes", DEFAULT_ALERTING_GAP)),
            "email_alerts_enabled":    rules_cfg.get(r["id"], {}).get("email_alerts_enabled", False),
        }
        for r in _all_known_rules(rules_cfg)
    ]
