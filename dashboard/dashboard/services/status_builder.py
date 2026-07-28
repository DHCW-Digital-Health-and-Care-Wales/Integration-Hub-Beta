"""
System-status and alarm-map builders shared across page routes and blueprints.

Extracted from ``dashboard.app`` so both the (soon-to-be) Flask blueprint
modules and ``app.py`` itself can import these pure/cache-backed helpers
without creating a circular import (blueprints import ``app`` to register
themselves; if these helpers stayed in ``app.py`` the blueprints could not
import them back).

These functions have no Flask dependency — they do not touch ``request``,
``session`` or ``render_template`` — so they are safe to import from any
module.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo

import dashboard.config as config
from dashboard.services import cache
from dashboard.services.alarm1 import get_alarm_status, get_config_page_data
from dashboard.services.alarm2 import get_alarm2_config_page_data, get_alarm2_status
from dashboard.services.alarm3 import get_alarm3_config_page_data, get_alarm3_status
from dashboard.services.azure_monitor import get_exceptions, get_retry_delay_metrics_by_flow
from dashboard.services.flows import build_flow_data, get_active_flows, overall_health
from dashboard.services.service_bus import get_queues

LONDON_TZ = ZoneInfo("Europe/London")


def get_cached_status(force: bool = False) -> dict:
    """Return the cached system status dict, optionally forcing a fresh rebuild."""
    if force:
        return cache.cached("status", build_status, force=True)
    return cache.cached_nowait("status", build_status)


def build_status() -> dict:
    """Fetch live Azure data and build the full system-status payload.

    Runs queue, active-flow, and exception queries concurrently to minimise
    latency on a cold-cache rebuild.
    """
    # Run the three independent Azure API calls concurrently to cut cold-cache
    # latency from ~3× to ~1× round-trip time.
    with ThreadPoolExecutor(max_workers=3) as pool:
        fut_queues = pool.submit(get_queues)
        fut_flows = pool.submit(get_active_flows)
        fut_exc = pool.submit(get_exceptions, hours=1)
        queues = fut_queues.result()
        active_flows = fut_flows.result()
        exceptions_1h = fut_exc.result()

    flows = build_flow_data(queues, active_flows)

    total_active = sum(q.get("active_message_count", 0) for q in queues)
    total_dlq = sum(q.get("dead_letter_message_count", 0) for q in queues)

    exception_count = len(exceptions_1h)

    flow_statuses = [f["health"] for f in flows]
    sys_health = overall_health(flow_statuses)
    healthy_count = flow_statuses.count("healthy")
    warning_count = flow_statuses.count("warning")
    critical_count = flow_statuses.count("critical")

    retry_metrics = get_retry_delay_metrics_by_flow(hours=1, min_delay_seconds=60)
    flow_labels = {flow.get("id"): flow.get("label", flow.get("id")) for flow in flows}
    retry_rows: list[dict] = []
    flows_over_1m = 0

    for metric in retry_metrics:
        flow_id = metric.get("workflow_id")
        delay_seconds = metric.get("delay_seconds")
        has_metric = delay_seconds is not None and isinstance(delay_seconds, (int, float))
        over_1m = bool(has_metric and delay_seconds and delay_seconds > 60)
        if over_1m:
            flows_over_1m += 1

        delay_display = (
            f"{int(delay_seconds)}s" if has_metric and delay_seconds is not None
            else "Metric unavailable"
        )
        retry_rows.append(
            {
                "workflow_id": flow_id,
                "flow_label": flow_labels.get(flow_id, flow_id),
                "delay_seconds": delay_seconds,
                "delay_display": delay_display,
                "attempt": metric.get("attempt"),
                "queue": metric.get("queue") or "",
                "microservice_id": metric.get("microservice_id") or "",
                "timestamp": metric.get("timestamp") or "",
                "status": "warning" if over_1m else "healthy",
                "over_1m": over_1m,
            }
        )

    return {
        "refreshed_at": datetime.now(LONDON_TZ).isoformat(),
        "system_health": sys_health,
        "kpis": {
            "total_active_messages": total_active,
            "total_dlq_messages": total_dlq,
            "exception_count_1h": exception_count,
            "flows_healthy": healthy_count,
            "flows_warning": warning_count,
            "flows_critical": critical_count,
        },
        "flows": flows,
        "queues": queues,
        "recent_exceptions": exceptions_1h[:5],
        "retry_delays": retry_rows,
        "retry_delay_kpis": {
            "flows_over_1m": flows_over_1m,
            "flows_reporting": len(retry_rows),
        },
    }


def build_alarm_map() -> dict[str, dict]:
    """Build a {workflow_id: {alarm1, alarm2, alarm3}} map for the Flows page.

    Config is read directly from JSON (fast).
    Live status is pulled from cache — non-blocking, may be absent on first load.
    """
    a1_cfg = {r["workflow_id"]: r for r in get_config_page_data() if r.get("workflow_id")}
    a2_cfg = {r["workflow_id"]: r for r in get_alarm2_config_page_data() if r.get("workflow_id")}
    a3_cfg = {r["workflow_id"]: r for r in get_alarm3_config_page_data() if r.get("workflow_id")}

    a1_rows, a2_rows, a3_rows = cache.multi_cached_nowait(
        [
            ("alarms", get_alarm_status, config.API_CACHE_TTL),
            ("alarm2", get_alarm2_status, config.API_CACHE_TTL),
            ("alarm3", get_alarm3_status, config.API_CACHE_TTL),
        ]
    )
    a1_status = {r["workflow_id"]: r["status"] for r in (a1_rows or [])}
    a2_status = {r["workflow_id"]: r["status"] for r in (a2_rows or [])}
    a3_status = {r["workflow_id"]: r["status"] for r in (a3_rows or [])}

    result: dict[str, dict] = {}
    for wid in set(a1_cfg) | set(a2_cfg) | set(a3_cfg):
        result[wid] = {
            "alarm1": {**a1_cfg[wid], "status": a1_status.get(wid)} if wid in a1_cfg else None,
            "alarm2": {**a2_cfg[wid], "status": a2_status.get(wid)} if wid in a2_cfg else None,
            "alarm3": {**a3_cfg[wid], "status": a3_status.get(wid)} if wid in a3_cfg else None,
        }
    return result


def email_alerts_configured() -> bool:
    """Whether alert emails can plausibly be sent (used to enable/disable UI controls).

    Does not perform a live Key Vault fetch — just checks that either a local ACS
    connection string or a Key Vault URL is configured, alongside a sender and recipient.
    Must mirror the guard in email_service.send_alert_email() so the UI never enables
    controls for a configuration that will silently fail to send.
    """
    acs_source_configured = bool(config.ACS_CONNECTION_STRING or config.AZURE_KEY_VAULT_URL)
    return bool(
        config.ALERT_EMAIL_ENABLED and acs_source_configured and config.ALERT_EMAIL_TO and config.ALERT_EMAIL_FROM
    )


def alarm_summary(rows: list[dict] | None) -> dict:
    """Compute a compact status count dict from an alarm rows list."""
    rows = rows or []
    return {
        "critical": sum(1 for r in rows if r.get("status") == "critical"),
        "suppressed": sum(1 for r in rows if r.get("status") == "suppressed"),
        "unknown": sum(1 for r in rows if r.get("status") == "unknown"),
        "healthy": sum(1 for r in rows if r.get("status") == "healthy"),
        "total": len(rows),
    }
