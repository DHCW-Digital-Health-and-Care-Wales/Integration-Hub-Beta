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
from dashboard.services import cache, flow_sources, network_test
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


def api_network_test_run() -> tuple[Response, int] | Response:
    """Run an on-demand TCP connect/latency test against a host:port and persist the result.

    Expects a JSON body of ``{"host": "...", "port": ...}``. Host/port are validated
    before touching any socket calls — invalid input gets a 400 rather than reaching
    ``network_test.run_latency_test``.
    """
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "JSON body must be an object"}), 400
    try:
        result = network_test.run_latency_test(payload.get("host", ""), payload.get("port", ""))
    except network_test.InvalidTargetError as _exc:
        return jsonify({"error": "Invalid host or port."}), 400

    # The test itself has already run and succeeded regardless of Cosmos's health —
    # a persistence failure is surfaced as a warning, not a failed test result.
    if not network_test.save_history_sample(result["host"], result["port"], result):
        result["history_warning"] = "Result could not be saved to history — the history store is unreachable."
    return jsonify(result)


def api_network_test_history() -> tuple[Response, int] | Response:
    """JSON endpoint returning recent latency history for a host:port pair (for the trend graph).

    ``DELETE`` permanently removes all stored history for that host:port instead.
    """
    try:
        host = network_test.validate_host(request.args.get("host", ""))
        port = network_test.validate_port(request.args.get("port", ""))
    except network_test.InvalidTargetError:
        return jsonify({"error": "Invalid host or port."}), 400

    if request.method == "DELETE":
        network_test.delete_history(host, port)
        return jsonify({"deleted": True, "host": host, "port": port})

    return jsonify({"host": host, "port": port, "samples": network_test.get_history(host, port)})


def api_network_test_list() -> Response:
    """JSON endpoint returning every tested host:port with its most recent result.

    Powers the endpoint list on the network test page.
    """
    return jsonify({"endpoints": network_test.list_tested_endpoints()})


def api_network_test_sources() -> tuple[Response, int] | Response:
    """GET returns every configured flow source server; POST adds one from a JSON body.

    Powers the Network Test configuration screen's table and "add" form.
    """
    if request.method == "POST":
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "JSON body must be an object"}), 400
        try:
            source = flow_sources.add_source(
                payload.get("description", ""), payload.get("url", ""), payload.get("port", "")
            )
        except flow_sources.InvalidSourceError as exc:
            return jsonify({"error": exc.safe_message}), 400
        except flow_sources.SourcePersistenceError as exc:
            return jsonify({"error": exc.safe_message}), 503
        return jsonify(source), 201

    return jsonify({"sources": flow_sources.list_sources()})


def api_network_test_source(source_id: str) -> tuple[Response, int] | Response:
    """PUT updates a flow source server from a JSON body; DELETE removes it."""
    if request.method == "DELETE":
        flow_sources.delete_source(source_id)
        return jsonify({"deleted": True, "id": source_id})

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "JSON body must be an object"}), 400
    try:
        source = flow_sources.update_source(
            source_id, payload.get("description", ""), payload.get("url", ""), payload.get("port", "")
        )
    except flow_sources.InvalidSourceError as exc:
        return jsonify({"error": exc.safe_message}), 400
    except flow_sources.SourcePersistenceError as exc:
        return jsonify({"error": exc.safe_message}), 503
    return jsonify(source)


# Uploaded CSV files are read fully into memory (they hold a handful of rows of plain
# text), so an explicit size cap guards against an oversized upload exhausting memory.
_MAX_IMPORT_CSV_BYTES = 1_000_000


def api_network_test_sources_import() -> tuple[Response, int] | Response:
    """POST a CSV file (multipart field "file") to bulk-import flow source servers."""
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return jsonify({"error": "No CSV file uploaded."}), 400

    raw = upload.read(_MAX_IMPORT_CSV_BYTES + 1)
    if len(raw) > _MAX_IMPORT_CSV_BYTES:
        return jsonify({"error": "CSV file is too large."}), 400

    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return jsonify({"error": "CSV file must be UTF-8 encoded."}), 400

    result = flow_sources.import_sources(content)
    if result["persistence_failed"]:
        return jsonify(result), 503
    return jsonify(result)


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
    app.add_url_rule(
        "/api/network-test/run", endpoint="api_network_test_run", view_func=api_network_test_run, methods=["POST"]
    )
    app.add_url_rule(
        "/api/network-test/history",
        endpoint="api_network_test_history",
        view_func=api_network_test_history,
        methods=["GET", "DELETE"],
    )
    app.add_url_rule("/api/network-test/list", endpoint="api_network_test_list", view_func=api_network_test_list)
    app.add_url_rule(
        "/api/network-test/sources",
        endpoint="api_network_test_sources",
        view_func=api_network_test_sources,
        methods=["GET", "POST"],
    )
    app.add_url_rule(
        "/api/network-test/sources/import",
        endpoint="api_network_test_sources_import",
        view_func=api_network_test_sources_import,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/network-test/sources/<source_id>",
        endpoint="api_network_test_source",
        view_func=api_network_test_source,
        methods=["PUT", "DELETE"],
    )
