"""Alarm service — workflow message inactivity monitoring (Alarm 1).

Config and state are persisted to Azure Cosmos DB (see :mod:`dashboard.services.cosmos_store`).
Config is stored as the ``config`` document and per-rule alarm state (last-fired
timestamps) as the ``state`` document, both in the ``alarm1`` partition. Pauses
are separate records managed by :mod:`dashboard.services.alarm_pauses`.

Each rule targets a specific workflow_id and has five settings:
  alarm_enabled            – bool, whether Alarm 1 is active for this rule
  workflow_id              – the workflow to monitor (parse_json(Properties)["workflow_id"])
  day_threshold_minutes    – minutes of inactivity during Day to trip the alarm
  evening_threshold_minutes – minutes of inactivity during Evening to trip the alarm
  weekend_threshold_minutes – minutes of inactivity during Weekend to trip the alarm
  alerting_gap_minutes     – how long after first alarm before it fires again

The applicable inactivity trip point is determined by the current time period
(day / evening / weekend).  ``alerting_gap_minutes`` is a single re-alarm gap that
applies regardless of period.  Once a rule returns to healthy the last-alarm
timestamp is cleared so the next inactivity event fires immediately.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from azure.monitor.query import LogsQueryStatus

from dashboard import config
from dashboard.services import alarm_base, alarm_pauses
from dashboard.services.alarm_time_utils import get_current_period
from dashboard.services.azure_monitor import _get_logs_client
from dashboard.services.email_service import dispatch_email, send_alert_email

log = logging.getLogger(__name__)

# Cosmos partition (alarm namespace) and document ids for this alarm's config/state.
COSMOS_PK = "alarm1"
CONFIG_DOC_ID = "config"
STATE_DOC_ID = "state"

# Defaults
DEFAULT_DAY_THRESHOLD = 60
DEFAULT_EVENING_THRESHOLD = 120
DEFAULT_WEEKEND_THRESHOLD = 240
DEFAULT_ALERTING_GAP = 60

# Two-stage lookback windows: check 2 days first (~15× less KQL data scanned
# for active flows) and only fall back to 30 days for workflows silent > 48 h.
_FAST_LOOKBACK_DAYS = 2
_FULL_LOOKBACK_DAYS = 30


# ---------------------------------------------------------------------------
# Config / state persistence
# ---------------------------------------------------------------------------


def load_alarm_config() -> dict:
    """Load alarm config from Cosmos DB. Returns empty config when none is stored."""
    return alarm_base.load_config(COSMOS_PK, CONFIG_DOC_ID)


def save_alarm_config(cfg: dict) -> None:
    """Persist alarm config to Cosmos DB."""
    alarm_base.save_config(COSMOS_PK, cfg, CONFIG_DOC_ID)


def _load_alarm_state() -> dict:
    """Load per-rule alarm state (last_alarm_at timestamps) from Cosmos. Returns empty state when none is stored."""
    return alarm_base.load_state(COSMOS_PK, STATE_DOC_ID)


def _save_alarm_state(state: dict) -> None:
    """Persist per-rule alarm state to Cosmos DB."""
    alarm_base.save_state(COSMOS_PK, state, STATE_DOC_ID)


# ---------------------------------------------------------------------------
# Time-period helpers
# ---------------------------------------------------------------------------


def _applicable_threshold(server_cfg: dict, now: datetime) -> int:
    """Return the inactivity trip threshold in minutes for the current time period."""
    period = get_current_period(now)
    if period == "weekend":
        return int(server_cfg.get("weekend_threshold_minutes", DEFAULT_WEEKEND_THRESHOLD))
    if period == "day":
        return int(server_cfg.get("day_threshold_minutes", DEFAULT_DAY_THRESHOLD))
    return int(server_cfg.get("evening_threshold_minutes", DEFAULT_EVENING_THRESHOLD))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _display_name(server_id: str) -> str:
    """Derive a human-readable display name from a Container App resource ID.

    Strips region/environment prefixes (e.g. ``uks-dev-``) and the trailing
    ``-ca`` suffix, then expands known abbreviations such as ``hl7``, ``phw``, ``mpi``.
    """
    # Handle Container App naming: uks-dev-phw-hl7server-ca → PHW HL7 Server
    # Strip known prefix/suffix patterns and normalise separators
    name = server_id
    # Remove trailing -ca suffix
    if name.endswith("-ca"):
        name = name[:-3]
    # Remove leading {location}-{env}- prefix (e.g. uks-dev-)
    parts = name.split("-")
    # Drop parts that look like region/env prefixes (short, non-descriptive)
    # Heuristic: drop first two parts if they're 3 chars or fewer (uks, dev)
    while len(parts) >= 2 and len(parts[0]) <= 4:  # noqa: PLR2004
        parts = parts[1:]
    name = " ".join(parts)
    # Expand common abbreviations
    name = re.sub(r"\bhl7server\b", "HL7 Server", name, flags=re.IGNORECASE)
    name = re.sub(r"\bhl7\b", "HL7", name, flags=re.IGNORECASE)
    name = re.sub(r"\bphw\b", "PHW", name, flags=re.IGNORECASE)
    name = re.sub(r"\bpims\b", "PIMS", name, flags=re.IGNORECASE)
    name = re.sub(r"\bmpi\b", "MPI", name, flags=re.IGNORECASE)
    name = re.sub(r"\bwds\b", "WDS", name, flags=re.IGNORECASE)
    name = re.sub(r"\bparis\b", "Paris", name, flags=re.IGNORECASE)
    name = re.sub(r"\bmosaiq\b", "Mosaiq", name, flags=re.IGNORECASE)
    name = re.sub(r"\bchemo\b", "ChemoCare", name, flags=re.IGNORECASE)
    return name.title() if name == name.lower() else name


def _format_duration(minutes: float) -> str:
    """Format a duration in minutes as a human-readable string (e.g. ``"2.5 hours"``)."""
    return alarm_base.format_duration(minutes)


def _parse_dt(raw: object) -> datetime | None:
    """Parse a datetime from a Log Analytics row value or ISO string."""
    return alarm_base.parse_log_analytics_datetime(raw)


# ---------------------------------------------------------------------------
# Log Analytics queries
# ---------------------------------------------------------------------------


def _query_last_message_times(safe_ids: list[str], lookback_days: int) -> dict[str, datetime | None] | None:
    """Run a single Log Analytics query for the most recent MESSAGE_RECEIVED over *lookback_days*.

    Returns ``{workflow_id: last_message_dt}`` on success, or ``None`` if the query failed.
    """
    ids_kql = ", ".join(f'"{w}"' for w in safe_ids)
    resource_filter = ""
    if config.AZURE_APP_INSIGHTS_RESOURCE_ID:
        resource_filter = f"\n    | where _ResourceId =~ '{config.AZURE_APP_INSIGHTS_RESOURCE_ID}'"

    # Pre-filter with KQL `has` / `has_any` before parse_json(Properties) so
    # Log Analytics uses its inverted term index instead of parsing every trace.
    query = f"""
    AppTraces
    | where TimeGenerated > ago({lookback_days}d){resource_filter}
    | where Message == "Integration Hub Event"
    | where Properties has "MESSAGE_RECEIVED"
    | where Properties has_any ({ids_kql})
    | extend workflow_id = tostring(parse_json(Properties)["workflow_id"])
    | where workflow_id in ({ids_kql})
    | summarize last_message = max(TimeGenerated) by workflow_id
    """
    try:
        client = _get_logs_client()
        response = client.query_workspace(
            workspace_id=config.AZURE_LOG_ANALYTICS_WORKSPACE_ID,
            query=query,
            timespan=timedelta(days=lookback_days),
        )
        if response.status != LogsQueryStatus.SUCCESS:
            log.warning("get_last_message_times_by_workflow: partial/failed query (lookback=%dd)", lookback_days)
            return None

        found: dict[str, datetime | None] = {}
        for table in response.tables:
            for row in table.rows:
                row_dict = dict(zip(table.columns, row))
                wid = (row_dict.get("workflow_id") or "").strip()
                ts = _parse_dt(row_dict.get("last_message"))
                if wid:
                    found[wid] = ts
        return found
    except Exception as exc:
        log.error("Failed to fetch last message times (lookback=%dd): %s", lookback_days, exc)
        return None


def get_last_message_times_by_workflow(workflow_ids: list[str]) -> dict[str, datetime | None]:
    """Query Log Analytics for the most recent MESSAGE_RECEIVED per workflow_id (30-day window).

    Uses a fast 2-day query first so active workflows avoid scanning 30 days of
    ``AppTraces``, falling back to a 30-day query only for workflows with no
    recent activity.
    """
    if not config.AZURE_LOG_ANALYTICS_WORKSPACE_ID or not workflow_ids:
        return {wid: None for wid in workflow_ids}

    safe_ids = list(dict.fromkeys(s for wid in workflow_ids if wid and (s := re.sub(r"[^a-zA-Z0-9\-_]", "", wid))))
    if not safe_ids:
        return {wid: None for wid in workflow_ids}

    found = _query_last_message_times(safe_ids, _FAST_LOOKBACK_DAYS)
    if found is None:
        return {wid: None for wid in workflow_ids}

    missing = [wid for wid in safe_ids if wid not in found]
    if missing:
        fallback = _query_last_message_times(missing, _FULL_LOOKBACK_DAYS)
        if fallback:
            found.update(fallback)

    return {wid: found.get(wid) for wid in workflow_ids}


# ---------------------------------------------------------------------------
# Email notification
# ---------------------------------------------------------------------------


def _send_alarm_email(
    rule_id: str,
    workflow_id: str,
    display_name: str,
    minutes_since: float,
    period_threshold: int,
    last_msg: datetime | None,
    now: datetime,
    email_alerts_enabled: bool = False,
    *,
    async_send: bool = False,
) -> None:
    """Send an HTML email via Azure Communication Services when Alarm 1 fires."""
    if not email_alerts_enabled:
        return

    period = get_current_period(now)
    period_label = {
        "day": "Day (Mon–Fri 09:00–17:00)",
        "evening": "Evening (Mon–Fri 17:00–09:00)",
        "weekend": "Weekend (Fri 17:00–Mon 09:00)",
    }.get(period, period.title())
    last_msg_str = last_msg.strftime("%d %b %Y  %H:%M:%S UTC") if last_msg else "Never / unknown"
    duration_str = _format_duration(minutes_since)

    subject = f"[Integration Hub] Alarm 1 — {display_name} inactivity ({duration_str})"
    body = f"""<html><body style="font-family:Arial,sans-serif;color:#333;max-width:600px;">
<h2 style="color:#c0392b;border-bottom:2px solid #c0392b;padding-bottom:8px;">
  &#x26A0; Integration Hub — Alarm 1: Message Inactivity
</h2>
<p style="color:#555;font-size:14px;">
  The following workflow has received no messages for longer than its configured threshold.
</p>
<table cellpadding="8" cellspacing="0"
       style="border-collapse:collapse;font-size:14px;width:100%;
              background:#f9f9f9;border:1px solid #ddd;border-radius:4px;">
  <tr style="background:#fff;">
    <td style="font-weight:bold;width:180px;border-bottom:1px solid #eee;">Rule</td>
    <td style="border-bottom:1px solid #eee;">{display_name}</td>
  </tr>
  <tr style="background:#fff;">
    <td style="font-weight:bold;border-bottom:1px solid #eee;">Workflow ID</td>
    <td style="border-bottom:1px solid #eee;font-family:monospace;">{workflow_id}</td>
  </tr>
  <tr>
    <td style="font-weight:bold;border-bottom:1px solid #eee;">Last Message (UTC)</td>
    <td style="border-bottom:1px solid #eee;">{last_msg_str}</td>
  </tr>
  <tr style="background:#fff;">
    <td style="font-weight:bold;border-bottom:1px solid #eee;">Inactive For</td>
    <td style="border-bottom:1px solid #eee;color:#c0392b;font-weight:bold;">{duration_str}</td>
  </tr>
  <tr>
    <td style="font-weight:bold;border-bottom:1px solid #eee;">Period / Threshold</td>
    <td style="border-bottom:1px solid #eee;">{period_label} — {period_threshold} min</td>
  </tr>
  <tr style="background:#fff;">
    <td style="font-weight:bold;">Fired At (UTC)</td>
    <td>{now.strftime("%d %b %Y  %H:%M:%S UTC")}</td>
  </tr>
</table>
<p style="font-size:12px;color:#999;margin-top:24px;">
  NHS Wales Integration Hub — automated alarm notification
</p>
</body></html>"""

    def _deliver() -> None:
        if not send_alert_email(subject, body) and config.ALERT_EMAIL_ENABLED:
            # send_alert_email() already logs a warning (missing config) or error (send
            # failure, e.g. ACS throttling) for real failure cases. When ALERT_EMAIL_ENABLED
            # is False, a False return is expected/intentional, so avoid a noisy log here.
            log.warning("Failed to send alarm 1 email for %s", rule_id)

    if async_send:
        dispatch_email(_deliver)
    else:
        _deliver()


# ---------------------------------------------------------------------------
# Pause / unpause helpers
# ---------------------------------------------------------------------------


def pause_alarm_rule(
    rule_id: str, duration_minutes: int | None, reason: str, requested_by: str
) -> dict:
    """Pause a specific Alarm 1 rule from now, for ``duration_minutes`` or indefinitely (``None``)."""
    return alarm_base.pause_rule_now(
        COSMOS_PK, _known_rule_workflows(), rule_id, duration_minutes, reason, requested_by
    )


def unpause_alarm_rule(rule_id: str) -> None:
    """Resume a specific Alarm 1 rule (raises ``PauseConflictError`` if paused by a wider pause)."""
    alarm_base.resume_rule(COSMOS_PK, _known_rule_workflows(), rule_id, "Alarm 1", STATE_DOC_ID)


def _known_rule_workflows() -> dict[str, str]:
    """Return ``{rule_id: workflow_id}`` for every non-deleted Alarm 1 rule."""
    return {r["id"]: (r.get("workflow_id") or "").strip() for r in get_config_page_data()}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_alarm_status() -> list[dict]:
    """Evaluate Alarm 1 for all enabled rules and return their status rows.

    Status values:
        'critical'   – in alarm condition, cooldown has expired (needs attention)
        'suppressed' – in alarm condition but within the re-alarm cooldown window
        'healthy'    – last message received within the inactivity threshold
        'unknown'    – no message data found in the 30-day lookback window
        'paused'     – covered by an active pause; not evaluated and no email sent

    Every row carries the pause fields from ``alarm_base.EMPTY_PAUSE_FIELDS`` (filled
    in when paused) plus ``scheduled_pause`` — the next upcoming pause, or ``None``.

    State (last_alarm_at per rule) is persisted to Cosmos DB so that
    cooldowns survive dashboard restarts.
    """
    cfg = load_alarm_config()
    rules_cfg = cfg.get("rules", {})

    enabled_rules = [
        (rid, rcfg) for rid, rcfg in rules_cfg.items() if not rcfg.get("deleted") and rcfg.get("alarm_enabled", False)
    ]
    if not enabled_rules:
        return []

    # Collect unique workflow_ids for the batch query
    workflow_ids = list(
        dict.fromkeys(
            rcfg.get("workflow_id", "").strip() for _, rcfg in enabled_rules if rcfg.get("workflow_id", "").strip()
        )
    )
    last_times = get_last_message_times_by_workflow(workflow_ids)
    now = datetime.now(timezone.utc)

    state = _load_alarm_state()
    state_rules = state.setdefault("rules", {})
    state_dirty = False
    pauses = alarm_pauses.list_pauses()

    results: list[dict] = []
    pending_emails: list[dict[str, Any]] = []

    for rid, rule_cfg in enabled_rules:
        workflow_id = rule_cfg.get("workflow_id", "").strip()
        period_threshold = _applicable_threshold(rule_cfg, now)
        last_msg = last_times.get(workflow_id) if workflow_id else None

        # Check for a pause before any alarm evaluation so no email can be sent.
        pause_fields = alarm_base.resolve_pause(
            state_rules.get(rid, {}), COSMOS_PK, rid, workflow_id, pauses, now
        )
        if pause_fields is not None:
            results.append(
                {
                    **_build_row(
                        rid,
                        rule_cfg,
                        last_msg=last_msg,
                        status="paused",
                        minutes_since=(now - last_msg).total_seconds() / 60 if last_msg else None,
                        cooldown_remaining=None,
                        now=now,
                    ),
                    **pause_fields,
                }
            )
            continue
        if alarm_base.clear_expired_legacy_pause(state_rules, rid, now):
            state_dirty = True

        if last_msg is None:
            results.append(
                _build_row(
                    rid,
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
                    rule_cfg,
                    last_msg=last_msg,
                    status="healthy",
                    minutes_since=minutes_since,
                    cooldown_remaining=None,
                    now=now,
                )
            )
            continue

        alerting_gap = int(rule_cfg.get("alerting_gap_minutes", DEFAULT_ALERTING_GAP))
        last_alarm_at = _parse_dt(state_rules.get(rid, {}).get("last_alarm_at"))
        display_name = rule_cfg.get("display_name") or workflow_id

        if last_alarm_at is None:
            status = "critical"
            state_rules.setdefault(rid, {})["last_alarm_at"] = now.isoformat()
            state_dirty = True
            cooldown_remaining = None
            pending_emails.append(
                {
                    "rule_id": rid,
                    "workflow_id": workflow_id,
                    "display_name": display_name,
                    "minutes_since": minutes_since,
                    "period_threshold": period_threshold,
                    "last_msg": last_msg,
                    "now": now,
                    "email_alerts_enabled": rule_cfg.get("email_alerts_enabled", False),
                }
            )
        else:
            mins_since_alarm = (now - last_alarm_at).total_seconds() / 60
            if mins_since_alarm >= alerting_gap:
                status = "critical"
                state_rules[rid]["last_alarm_at"] = now.isoformat()
                state_dirty = True
                cooldown_remaining = None
                pending_emails.append(
                    {
                        "rule_id": rid,
                        "workflow_id": workflow_id,
                        "display_name": display_name,
                        "minutes_since": minutes_since,
                        "period_threshold": period_threshold,
                        "last_msg": last_msg,
                        "now": now,
                        "email_alerts_enabled": rule_cfg.get("email_alerts_enabled", False),
                    }
                )
            else:
                status = "suppressed"
                cooldown_remaining = alerting_gap - mins_since_alarm

        results.append(
            _build_row(
                rid,
                rule_cfg,
                last_msg=last_msg,
                status=status,
                minutes_since=minutes_since,
                cooldown_remaining=cooldown_remaining,
                now=now,
            )
        )

    if state_dirty:
        _save_alarm_state({"rules": state_rules})

    for email_kwargs in pending_emails:
        _send_alarm_email(**email_kwargs, async_send=True)

    alarm_pauses.annotate_scheduled(results, COSMOS_PK, pauses, now)
    _order = {"paused": 0, "critical": 1, "suppressed": 2, "unknown": 3, "healthy": 4}
    results.sort(key=lambda r: _order.get(r["status"], 9))
    return results


def _build_row(
    rid: str,
    rule_cfg: dict,
    last_msg: datetime | None,
    status: str,
    minutes_since: float | None,
    cooldown_remaining: float | None,
    now: datetime,
) -> dict:
    """Build the status-row dict for a single Alarm 1 rule."""
    period = get_current_period(now)
    period_threshold = _applicable_threshold(rule_cfg, now)
    workflow_id = rule_cfg.get("workflow_id", "").strip()
    return {
        "id": rid,
        "display_name": rule_cfg.get("display_name") or workflow_id or rid,
        "workflow_id": workflow_id,
        "day_threshold_minutes": int(rule_cfg.get("day_threshold_minutes", DEFAULT_DAY_THRESHOLD)),
        "evening_threshold_minutes": int(rule_cfg.get("evening_threshold_minutes", DEFAULT_EVENING_THRESHOLD)),
        "weekend_threshold_minutes": int(rule_cfg.get("weekend_threshold_minutes", DEFAULT_WEEKEND_THRESHOLD)),
        "alerting_gap_minutes": int(rule_cfg.get("alerting_gap_minutes", DEFAULT_ALERTING_GAP)),
        "current_period": period,
        "period_threshold_minutes": period_threshold,
        "last_message": last_msg.isoformat() if last_msg else None,
        "last_message_display": (last_msg.strftime("%d %b %Y  %H:%M:%S UTC") if last_msg else "Never / unknown"),
        "status": status,
        "minutes_since": round(minutes_since, 1) if minutes_since is not None else None,
        "duration_label": _format_duration(minutes_since) if minutes_since is not None else "No data",
        "cooldown_remaining": round(cooldown_remaining, 0) if cooldown_remaining is not None else None,
        **alarm_base.EMPTY_PAUSE_FIELDS,
    }


def get_config_page_data() -> list[dict]:
    """Return all configured (non-deleted) rules with their current alarm settings."""
    cfg = load_alarm_config()
    rules_cfg = cfg.get("rules", {})

    return [
        {
            "id": rid,
            "display_name": rcfg.get("display_name") or rcfg.get("workflow_id", rid),
            "workflow_id": rcfg.get("workflow_id", ""),
            "alarm_enabled": rcfg.get("alarm_enabled", False),
            "day_threshold_minutes": int(rcfg.get("day_threshold_minutes", DEFAULT_DAY_THRESHOLD)),
            "evening_threshold_minutes": int(rcfg.get("evening_threshold_minutes", DEFAULT_EVENING_THRESHOLD)),
            "weekend_threshold_minutes": int(rcfg.get("weekend_threshold_minutes", DEFAULT_WEEKEND_THRESHOLD)),
            "alerting_gap_minutes": int(rcfg.get("alerting_gap_minutes", DEFAULT_ALERTING_GAP)),
            "email_alerts_enabled": rcfg.get("email_alerts_enabled", False),
            "email_ooh_enabled": rcfg.get("email_ooh_enabled", False) and rcfg.get("email_alerts_enabled", False),
        }
        for rid, rcfg in rules_cfg.items()
        if not rcfg.get("deleted")
    ]


def generate_rule_id(workflow_id: str, existing_ids: set[str]) -> str:
    """Return a safe config key for a new rule, deduplicating if needed."""
    base = re.sub(r"[^a-z0-9\-]", "-", workflow_id.lower().strip()).strip("-")
    base = re.sub(r"-{2,}", "-", base) or "rule"
    candidate = f"{base}-inactivity"
    if candidate not in existing_ids:
        return candidate
    for n in range(2, 9999):
        c = f"{base}-inactivity-{n}"
        if c not in existing_ids:
            return c
    return candidate
