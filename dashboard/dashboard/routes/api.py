"""JSON API routes consumed by dashboard.js for live-updating widgets.

Extracted from ``dashboard.app`` as part of the route-module split. These are
plain view functions (no Flask ``Blueprint`` — see ``dashboard.routes``
module docstring for why), registered onto the app by ``register(app)`` with
explicit endpoint names matching their original flat names so existing
``url_for(...)`` calls and any programmatic references keep working
unchanged.
"""

from __future__ import annotations

from datetime import datetime

from flask import Flask, Response, jsonify, request

import dashboard.config as config
from dashboard.services import cache
from dashboard.services.alarm1 import get_alarm_status
from dashboard.services.alarm2 import get_alarm2_status
from dashboard.services.alarm3 import get_alarm3_status
from dashboard.services.arm import discover_flows
from dashboard.services.azure_monitor import (
    get_container_app_metric_history,
    get_hl7_throughput_metrics,
    get_messages_today,
)
from dashboard.services.container_apps import get_container_apps_metrics
from dashboard.services.flows import build_flow_data, get_active_flows
from dashboard.services.service_bus import get_message_metrics, get_queues
from dashboard.services.status_builder import LONDON_TZ, alarm_summary, get_cached_status


def healthz() -> dict:
    """Lightweight health check endpoint. Returns immediately without Azure calls."""
    return {"status": "ok"}


def api_status() -> Response:
    """JSON endpoint returning current system status plus compact alarm summaries.

    Accepts ``?force=true`` to bypass the cache and force a fresh Azure query.
    """
    force = request.args.get("force", "false").lower() == "true"
    data = get_cached_status(force=force)
    # Merge compact alarm summaries so dashboard.js can keep widgets live.
    # These are non-blocking cache reads — no extra Azure calls.
    alarm1_rows, alarm2_rows, alarm3_rows = cache.multi_cached_nowait(
        [
            ("alarms", get_alarm_status, config.API_CACHE_TTL),
            ("alarm2", get_alarm2_status, config.API_CACHE_TTL),
            ("alarm3", get_alarm3_status, config.API_CACHE_TTL),
        ]
    )
    data = dict(data)
    data["alarm1_summary"] = alarm_summary(alarm1_rows)
    data["alarm2_summary"] = alarm_summary(alarm2_rows)
    data["alarm3_summary"] = alarm_summary(alarm3_rows)
    return jsonify(data)


def api_refresh() -> Response:
    """Force-refresh all caches including ARM flow discovery."""
    discover_flows(force=True)
    # Bust every cache entry
    with cache.cache_lock:
        for entry in cache.cache_data.values():
            entry["ts"] = 0.0
    data = get_cached_status(force=True)
    return jsonify({"refreshed": True, "active_flows": list(get_active_flows().keys()), **data})


def api_flows() -> Response:
    """JSON endpoint returning live flow health and container-app metrics."""
    queues = get_queues()
    active_flows = get_active_flows()
    flows = build_flow_data(queues, active_flows)
    container_metrics = get_container_apps_metrics()
    return jsonify(
        {
            "flows": flows,
            "container_metrics": container_metrics,
        }
    )


def api_container_app_history(name: str) -> Response:
    """JSON endpoint returning CPU% and memory (MiB) history for a Container App.

    Query params:
        hours: window size — one of 1, 6, 24, 168 (defaults to 1).
    """
    hours_raw = request.args.get("hours", "1", type=str)
    allowed = {"1": 1, "6": 6, "24": 24, "168": 168}
    hours = allowed.get(hours_raw, 1)
    history = get_container_app_metric_history(name, hours=hours)
    return jsonify(history)


def api_messages() -> Response:
    """JSON endpoint returning all messages processed today."""
    messages = get_messages_today()
    return jsonify({"messages": messages, "count": len(messages)})


def api_servicebus_metrics() -> Response:
    """JSON endpoint returning Service Bus message-count metrics for a given time window.

    Query params:
        hours: one of 1, 6, 12, 24, 168, 720 (defaults to 1).
        queue:  optional queue name filter.
    """
    hours = request.args.get("hours", "1", type=str)
    allowed = {"1": 1, "6": 6, "12": 12, "24": 24, "168": 168, "720": 720}
    timespan_hours = allowed.get(hours, 1)
    queue = request.args.get("queue", "").strip() or None
    metrics = get_message_metrics(timespan_hours, queue_name=queue)
    return jsonify(metrics)


def api_hl7_throughput() -> Response:
    """JSON endpoint returning HL7 message throughput metrics (messages in and out).

    Query params:
        hours: one of 24, 72, 168, 336, 720 (defaults to 24) — i.e. last
            24 hours, 3, 7, 14 or 30 days.
        health_board: optional health board filter (e.g. PHW).
        service: optional service / flow filter (e.g. phw-to-mpi).
    """
    hours = request.args.get("hours", "24", type=str)
    allowed = {"24": 24, "72": 72, "168": 168, "336": 336, "720": 720}
    timespan_hours = allowed.get(hours, 24)
    health_board = request.args.get("health_board", "").strip() or None
    service = request.args.get("service", "").strip() or None
    metrics = get_hl7_throughput_metrics(
        hours=timespan_hours,
        health_board=health_board,
        service=service,
    )
    return jsonify(metrics)


def api_alarms_status() -> Response:
    """JSON endpoint returning all three alarm statuses in parallel.

    Supports ``?refresh=1`` to force a cache bust.  Useful for async page
    loading or periodic polling from the browser.
    """
    force = request.args.get("refresh") == "1"
    if force:
        with cache.cache_lock:
            cache.cache_data["alarms"]["ts"] = 0.0
            cache.cache_data["alarm2"]["ts"] = 0.0
            cache.cache_data["alarm3"]["ts"] = 0.0

    alarm1_rows, alarm2_rows, alarm3_rows = cache.multi_cached_nowait(
        [
            ("alarms", get_alarm_status, config.API_CACHE_TTL),
            ("alarm2", get_alarm2_status, config.API_CACHE_TTL),
            ("alarm3", get_alarm3_status, config.API_CACHE_TTL),
        ]
    )
    return jsonify(
        {
            "alarm1": alarm1_rows,
            "alarm2": alarm2_rows,
            "alarm3": alarm3_rows,
            "refreshed_at": datetime.now(LONDON_TZ).isoformat(),
            "poll_interval_seconds": int(config.API_CACHE_TTL),
        }
    )


def register(app: Flask) -> None:
    """Register every API route onto ``app`` with its original flat endpoint name."""
    app.add_url_rule("/healthz", endpoint="healthz", view_func=healthz)
    app.add_url_rule("/api/status", endpoint="api_status", view_func=api_status)
    app.add_url_rule("/api/refresh", endpoint="api_refresh", view_func=api_refresh)
    app.add_url_rule("/api/flows", endpoint="api_flows", view_func=api_flows)
    app.add_url_rule(
        "/api/container-app/<name>/history",
        endpoint="api_container_app_history",
        view_func=api_container_app_history,
    )
    app.add_url_rule("/api/messages", endpoint="api_messages", view_func=api_messages)
    app.add_url_rule("/api/servicebus-metrics", endpoint="api_servicebus_metrics", view_func=api_servicebus_metrics)
    app.add_url_rule("/api/hl7-throughput", endpoint="api_hl7_throughput", view_func=api_hl7_throughput)
    app.add_url_rule("/api/alarms/status", endpoint="api_alarms_status", view_func=api_alarms_status)
