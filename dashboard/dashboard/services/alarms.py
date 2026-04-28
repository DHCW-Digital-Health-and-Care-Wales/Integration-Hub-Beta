"""Alarm service — HL7 server message inactivity monitoring (Alarm 1).

Config is persisted to ``alarm_config.json`` in the dashboard root directory.
State (last alarm fired time per server) is persisted to ``alarm_state.json``.

Each HL7 server has five settings:
  alarm_enabled            – bool, whether Alarm 1 is active for this server
  day_threshold_minutes    – minutes of inactivity during Day to trip the alarm
  evening_threshold_minutes – minutes of inactivity during Evening to trip the alarm
  weekend_threshold_minutes – minutes of inactivity during Weekend to trip the alarm
  alerting_gap_minutes     – how long after first alarm before it fires again

The applicable inactivity trip point is determined by the current time period
(day / evening / weekend).  ``alerting_gap_minutes`` is a single re-alarm gap that
applies regardless of period.  Once a server returns to healthy the last-alarm
timestamp is cleared so the next inactivity event fires immediately.
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

CONFIG_PATH = Path(__file__).parent.parent.parent / "alarm_config.json"
STATE_PATH  = Path(__file__).parent.parent.parent / "alarm_state.json"

# Defaults
DEFAULT_DAY_THRESHOLD     = 60
DEFAULT_EVENING_THRESHOLD = 120
DEFAULT_WEEKEND_THRESHOLD = 240
DEFAULT_ALERTING_GAP      = 60

# Seed list — always present even if Log Analytics is unavailable.
KNOWN_HL7_SERVERS: list[str] = [
    "chemocare_hl7_server",
    "paris_hl7_server",
    "phw_hl7_server",
    "pims_hl7_server",
]


# ---------------------------------------------------------------------------
# Config / state persistence
# ---------------------------------------------------------------------------

def load_alarm_config() -> dict:
    """Load alarm config from JSON file. Returns empty config on missing/corrupt file."""
    if not CONFIG_PATH.exists():
        return {"servers": {}}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Failed to load alarm config: %s", exc)
        return {"servers": {}}


def save_alarm_config(cfg: dict) -> None:
    """Persist alarm config to JSON file."""
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, default=str), encoding="utf-8")


def _load_alarm_state() -> dict:
    if not STATE_PATH.exists():
        return {"servers": {}}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Failed to load alarm state: %s", exc)
        return {"servers": {}}


def _save_alarm_state(state: dict) -> None:
    try:
        STATE_PATH.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    except OSError as exc:
        log.error("Failed to save alarm state: %s", exc)


# ---------------------------------------------------------------------------
# Time-period helpers
# ---------------------------------------------------------------------------

def get_current_period(now: datetime) -> str:
    """Return the current time period: 'day', 'evening', or 'weekend'.

    Weekend : Friday 17:00 → Monday 08:00 (UTC)
    Day     : Monday–Friday 08:00–17:00 (UTC)
    Evening : Monday–Friday 17:00–08:00, excluding weekend window (UTC)
    """
    weekday = now.weekday()   # 0 = Monday … 4 = Friday, 5 = Sat, 6 = Sun
    time_mins = now.hour * 60 + now.minute
    DAY_START = 8 * 60    # 08:00
    DAY_END   = 17 * 60   # 17:00

    # Weekend window: Fri 17:00 → Mon 08:00
    if weekday == 4 and time_mins >= DAY_END:   # Friday after 17:00
        return "weekend"
    if weekday in (5, 6):                        # Saturday, Sunday
        return "weekend"
    if weekday == 0 and time_mins < DAY_START:   # Monday before 08:00
        return "weekend"

    # Day window: Mon–Fri 08:00–17:00
    if 0 <= weekday <= 4 and DAY_START <= time_mins < DAY_END:
        return "day"

    # Everything else is evening
    return "evening"


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
    return server_id.replace("_", " ").title()


def _format_duration(minutes: float) -> str:
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


def _parse_dt(raw: object) -> datetime | None:
    """Parse a datetime from a Log Analytics row value or ISO string."""
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(raw))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Log Analytics queries
# ---------------------------------------------------------------------------

def discover_hl7_servers() -> list[str]:
    """Return all known HL7 server microservice_ids (seed list + Log Analytics discovery)."""
    discovered: list[str] = []

    if config.AZURE_LOG_ANALYTICS_WORKSPACE_ID:
        query = """
        AppTraces
        | where TimeGenerated > ago(30d)
        | where Message == "Integration Hub Event"
        | where Properties contains "MESSAGE_RECEIVED"
        | extend microservice_id = tostring(parse_json(Properties)["microservice_id"])
        | where microservice_id endswith "_hl7_server"
        | summarize by microservice_id
        | order by microservice_id asc
        """
        try:
            client = LogsQueryClient(get_azure_credential())
            response = client.query_workspace(
                workspace_id=config.AZURE_LOG_ANALYTICS_WORKSPACE_ID,
                query=query,
                timespan=timedelta(days=30),
            )
            if response.status == LogsQueryStatus.SUCCESS:
                for table in response.tables:
                    for row in table.rows:
                        row_dict = dict(zip(table.columns, row))
                        mid = (row_dict.get("microservice_id") or "").strip()
                        if mid:
                            discovered.append(mid)
        except Exception as exc:
            log.error("Failed to discover HL7 servers: %s", exc)

    return sorted(dict.fromkeys(KNOWN_HL7_SERVERS + discovered))


def get_last_message_times(server_ids: list[str]) -> dict[str, datetime | None]:
    """Query Log Analytics for the most recent MESSAGE_RECEIVED per server (30-day window)."""
    if not config.AZURE_LOG_ANALYTICS_WORKSPACE_ID or not server_ids:
        return {sid: None for sid in server_ids}

    safe_ids = [re.sub(r"[^a-zA-Z0-9\-_]", "", sid) for sid in server_ids if sid]
    if not safe_ids:
        return {sid: None for sid in server_ids}

    ids_kql = ", ".join(f'"{s}"' for s in safe_ids)
    query = f"""
    AppTraces
    | where TimeGenerated > ago(30d)
    | where Message == "Integration Hub Event"
    | where Properties contains "MESSAGE_RECEIVED"
    | extend microservice_id = tostring(parse_json(Properties)["microservice_id"])
    | where microservice_id in ({ids_kql})
    | summarize last_message = max(TimeGenerated) by microservice_id
    """
    try:
        client = LogsQueryClient(get_azure_credential())
        response = client.query_workspace(
            workspace_id=config.AZURE_LOG_ANALYTICS_WORKSPACE_ID,
            query=query,
            timespan=timedelta(days=30),
        )
        if response.status != LogsQueryStatus.SUCCESS:
            log.warning("get_last_message_times: partial/failed query")
            return {sid: None for sid in server_ids}

        found: dict[str, datetime | None] = {}
        for table in response.tables:
            for row in table.rows:
                row_dict = dict(zip(table.columns, row))
                mid = (row_dict.get("microservice_id") or "").strip()
                ts = _parse_dt(row_dict.get("last_message"))
                if mid:
                    found[mid] = ts

        return {sid: found.get(sid) for sid in server_ids}

    except Exception as exc:
        log.error("Failed to fetch last message times: %s", exc)
        return {sid: None for sid in server_ids}


# ---------------------------------------------------------------------------
# Email notification
# ---------------------------------------------------------------------------

def _send_alarm_email(
    server_id: str,
    display_name: str,
    minutes_since: float,
    period_threshold: int,
    last_msg: datetime | None,
    now: datetime,
    email_alerts_enabled: bool = False,
) -> None:
    """Send an HTML email via Azure Communication Services when Alarm 1 fires."""
    if not config.ALERT_EMAIL_ENABLED:
        return
    if not email_alerts_enabled:
        return
    if not config.ACS_CONNECTION_STRING or not config.ALERT_EMAIL_TO:
        log.warning("Alarm email enabled but ACS_CONNECTION_STRING / ALERT_EMAIL_TO not set — skipping")
        return

    period = get_current_period(now)
    period_label = {"day": "Day (Mon–Fri 08:00–17:00)", "evening": "Evening (Mon–Fri 17:00–08:00)",
                    "weekend": "Weekend (Fri 17:00–Mon 08:00)"}.get(period, period.title())
    last_msg_str = last_msg.strftime("%d %b %Y  %H:%M:%S UTC") if last_msg else "Never / unknown"
    duration_str = _format_duration(minutes_since)

    subject = f"[Integration Hub] Alarm 1 — {display_name} inactivity ({duration_str})"
    body = f"""<html><body style="font-family:Arial,sans-serif;color:#333;max-width:600px;">
<h2 style="color:#c0392b;border-bottom:2px solid #c0392b;padding-bottom:8px;">
  &#x26A0; Integration Hub — Alarm 1: Message Inactivity
</h2>
<p style="color:#555;font-size:14px;">
  The following HL7 server has received no messages for longer than its configured threshold.
</p>
<table cellpadding="8" cellspacing="0"
       style="border-collapse:collapse;font-size:14px;width:100%;
              background:#f9f9f9;border:1px solid #ddd;border-radius:4px;">
  <tr style="background:#fff;">
    <td style="font-weight:bold;width:180px;border-bottom:1px solid #eee;">Server</td>
    <td style="border-bottom:1px solid #eee;">{display_name}</td>
  </tr>
  <tr style="background:#fff;">
    <td style="font-weight:bold;border-bottom:1px solid #eee;">Server ID</td>
    <td style="border-bottom:1px solid #eee;font-family:monospace;">{server_id}</td>
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

    try:
        from azure.communication.email import EmailClient  # noqa: PLC0415

        client = EmailClient.from_connection_string(config.ACS_CONNECTION_STRING)
        message = {
            "senderAddress": config.ALERT_EMAIL_FROM,
            "recipients": {"to": [{"address": config.ALERT_EMAIL_TO}]},
            "content": {"subject": subject, "html": body},
        }
        poller = client.begin_send(message)
        poller.result()  # wait for delivery confirmation
        log.info("Alarm 1 email sent for %s to %s", server_id, config.ALERT_EMAIL_TO)
    except Exception as exc:
        log.error("Failed to send alarm 1 email for %s: %s", server_id, exc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_alarm_status() -> list[dict]:
    """Evaluate Alarm 1 for all enabled servers and return their status rows.

    Status values:
        'critical'   – in alarm condition, cooldown has expired (needs attention)
        'suppressed' – in alarm condition but within the re-alarm cooldown window
        'healthy'    – last message received within the inactivity threshold
        'unknown'    – no message data found in the 30-day lookback window

    State (last_alarm_at per server) is persisted to alarm_state.json so that
    cooldowns survive dashboard restarts.
    """
    cfg = load_alarm_config()
    servers_cfg = cfg.get("servers", {})

    all_ids = discover_hl7_servers()
    for sid in servers_cfg:
        if sid not in all_ids:
            all_ids.append(sid)
    all_ids.sort()

    enabled_ids = [sid for sid in all_ids if servers_cfg.get(sid, {}).get("alarm_enabled", False)]
    if not enabled_ids:
        return []

    last_times = get_last_message_times(enabled_ids)
    now = datetime.now(timezone.utc)

    state = _load_alarm_state()
    state_servers = state.setdefault("servers", {})
    state_dirty = False

    results: list[dict] = []

    for sid in enabled_ids:
        server_cfg = servers_cfg.get(sid, {})
        period_threshold = _applicable_threshold(server_cfg, now)
        last_msg = last_times.get(sid)

        if last_msg is None:
            # No data in 30-day window — cannot determine status
            results.append(_build_row(
                sid, server_cfg,
                last_msg=None,
                status="unknown",
                minutes_since=None,
                cooldown_remaining=None,
                now=now,
            ))
            continue

        minutes_since = (now - last_msg).total_seconds() / 60
        in_alarm = minutes_since > period_threshold

        if not in_alarm:
            # Healthy — clear any stored last-alarm timestamp
            if sid in state_servers:
                del state_servers[sid]
                state_dirty = True
            results.append(_build_row(
                sid, server_cfg,
                last_msg=last_msg,
                status="healthy",
                minutes_since=minutes_since,
                cooldown_remaining=None,
                now=now,
            ))
            continue

        # --- In alarm condition ---
        alerting_gap = int(server_cfg.get("alerting_gap_minutes", DEFAULT_ALERTING_GAP))
        last_alarm_at = _parse_dt(state_servers.get(sid, {}).get("last_alarm_at"))

        if last_alarm_at is None:
            # First alarm — fire immediately
            status = "critical"
            state_servers.setdefault(sid, {})["last_alarm_at"] = now.isoformat()
            state_dirty = True
            cooldown_remaining = None
            _send_alarm_email(sid, server_cfg.get("display_name") or _display_name(sid),
                              minutes_since, period_threshold, last_msg, now,
                              email_alerts_enabled=server_cfg.get("email_alerts_enabled", False))
        else:
            mins_since_alarm = (now - last_alarm_at).total_seconds() / 60
            if mins_since_alarm >= alerting_gap:
                # Alerting gap expired — fire again
                status = "critical"
                state_servers[sid]["last_alarm_at"] = now.isoformat()
                state_dirty = True
                cooldown_remaining = None
                _send_alarm_email(sid, server_cfg.get("display_name") or _display_name(sid),
                                  minutes_since, period_threshold, last_msg, now,
                                  email_alerts_enabled=server_cfg.get("email_alerts_enabled", False))
            else:
                # Within alerting gap — suppress
                status = "suppressed"
                cooldown_remaining = alerting_gap - mins_since_alarm

        results.append(_build_row(
            sid, server_cfg,
            last_msg=last_msg,
            status=status,
            minutes_since=minutes_since,
            cooldown_remaining=cooldown_remaining,
            now=now,
        ))

    if state_dirty:
        _save_alarm_state({"servers": state_servers})

    _order = {"critical": 0, "suppressed": 1, "unknown": 2, "healthy": 3}
    results.sort(key=lambda r: _order.get(r["status"], 9))
    return results


def _build_row(
    sid: str,
    server_cfg: dict,
    last_msg: datetime | None,
    status: str,
    minutes_since: float | None,
    cooldown_remaining: float | None,
    now: datetime,
) -> dict:
    period = get_current_period(now)
    period_threshold = _applicable_threshold(server_cfg, now)
    return {
        "id": sid,
        "display_name": server_cfg.get("display_name") or _display_name(sid),
        "day_threshold_minutes": int(server_cfg.get("day_threshold_minutes", DEFAULT_DAY_THRESHOLD)),
        "evening_threshold_minutes": int(server_cfg.get("evening_threshold_minutes", DEFAULT_EVENING_THRESHOLD)),
        "weekend_threshold_minutes": int(server_cfg.get("weekend_threshold_minutes", DEFAULT_WEEKEND_THRESHOLD)),
        "alerting_gap_minutes": int(server_cfg.get("alerting_gap_minutes", DEFAULT_ALERTING_GAP)),
        "current_period": period,
        "period_threshold_minutes": period_threshold,
        "last_message": last_msg.isoformat() if last_msg else None,
        "last_message_display": (
            last_msg.strftime("%d %b %Y  %H:%M:%S UTC") if last_msg else "Never / unknown"
        ),
        "status": status,
        "minutes_since": round(minutes_since, 1) if minutes_since is not None else None,
        "duration_label": _format_duration(minutes_since) if minutes_since is not None else "No data",
        "cooldown_remaining": round(cooldown_remaining, 0) if cooldown_remaining is not None else None,
    }


def get_config_page_data() -> list[dict]:
    """Return all known servers with their current alarm settings for the config form."""
    cfg = load_alarm_config()
    servers_cfg = cfg.get("servers", {})

    all_ids = discover_hl7_servers()
    for sid in servers_cfg:
        if sid not in all_ids:
            all_ids.append(sid)
    all_ids.sort()

    return [
        {
            "id": sid,
            "display_name": servers_cfg.get(sid, {}).get("display_name") or _display_name(sid),
            "alarm_enabled": servers_cfg.get(sid, {}).get("alarm_enabled", False),
            "day_threshold_minutes": int(
                servers_cfg.get(sid, {}).get("day_threshold_minutes", DEFAULT_DAY_THRESHOLD)
            ),
            "evening_threshold_minutes": int(
                servers_cfg.get(sid, {}).get("evening_threshold_minutes", DEFAULT_EVENING_THRESHOLD)
            ),
            "weekend_threshold_minutes": int(
                servers_cfg.get(sid, {}).get("weekend_threshold_minutes", DEFAULT_WEEKEND_THRESHOLD)
            ),
            "alerting_gap_minutes": int(
                servers_cfg.get(sid, {}).get("alerting_gap_minutes", DEFAULT_ALERTING_GAP)
            ),
            "email_alerts_enabled": servers_cfg.get(sid, {}).get("email_alerts_enabled", False),
        }
        for sid in all_ids
    ]
