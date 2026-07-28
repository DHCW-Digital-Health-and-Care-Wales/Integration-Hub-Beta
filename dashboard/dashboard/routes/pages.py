"""Page routes: full-page (HTML) views of the dashboard.

Extracted from ``dashboard.app`` as part of the route-module split. These are
plain view functions (no Flask ``Blueprint``) registered onto the app by
``register(app)`` with explicit endpoint names matching their original flat
names (e.g. ``endpoint="index"``), so existing ``url_for("index")``-style
calls in the Jinja templates continue to resolve without any template
changes.
"""

from __future__ import annotations

from urllib.parse import urlparse

from flask import Flask, Response, make_response, redirect, render_template, request, session, url_for

import dashboard.config as config
from dashboard.services import cache
from dashboard.services.alarm1 import get_alarm_status, load_alarm_config
from dashboard.services.alarm2 import get_alarm2_status, load_alarm2_config
from dashboard.services.alarm3 import get_alarm3_status, load_alarm3_config
from dashboard.services.arm import queue_to_microservice_ids
from dashboard.services.azure_monitor import get_exceptions, get_messages_today, get_throughput_filter_options
from dashboard.services.container_apps import get_container_apps_metrics
from dashboard.services.flows import build_flow_data, get_flows, queue_to_workflow_id
from dashboard.services.service_bus import get_queues
from dashboard.services.status_builder import build_alarm_map, get_cached_status
from dashboard.services.traces import get_trace


def set_language() -> Response:
    """Set the UI language preference in the session and redirect back to the referring page."""
    lang = request.form.get("lang", "en")
    if lang in ("en", "cy"):
        session["lang"] = lang

    # Never forward the raw Referer header to redirect(): it is client-supplied and
    # can be spoofed (and some browsers normalise "\" to "/" when resolving a
    # redirect, enabling a network-path-reference bypass e.g. "/\evil.com"). Instead
    # normalise backslashes and rebuild the target from only its path/query, which
    # discards any scheme/host entirely so the redirect can never leave this site.
    referrer = request.referrer
    if not referrer:
        return make_response(redirect(url_for("index")))

    parsed = urlparse(referrer.replace("\\", "/"))
    path = parsed.path or "/"
    target = f"{path}?{parsed.query}" if parsed.query else path
    return make_response(redirect(target))


def index() -> str:
    """Render the dashboard overview page with system status and alarm summaries."""
    status = get_cached_status()
    alarm1_rows, alarm2_rows, alarm3_rows = cache.multi_cached_nowait(
        [
            ("alarms", get_alarm_status, config.API_CACHE_TTL),
            ("alarm2", get_alarm2_status, config.API_CACHE_TTL),
            ("alarm3", get_alarm3_status, config.API_CACHE_TTL),
        ]
    )
    cfg1 = load_alarm_config()
    cfg2 = load_alarm2_config()
    cfg3 = load_alarm3_config()
    # Filter options change rarely, so cache them for longer than the live status.
    throughput_filters = cache.cached_nowait(
        "throughput_filters", get_throughput_filter_options, ttl=300
    ) or {"health_boards": [], "services": []}
    return render_template(
        "index.html",
        status=status,
        refresh_interval=config.API_CACHE_TTL,
        data_is_stale=cache.is_cache_stale("status"),
        splash_enabled=config.SPLASH_SCREEN_ENABLED,
        alarm1_rows=alarm1_rows or [],
        alarm2_rows=alarm2_rows or [],
        alarm3_rows=alarm3_rows or [],
        no_alarm1_configured=not any(r.get("alarm_enabled", False) for r in cfg1.get("rules", {}).values()),
        no_alarm2_configured=not any(r.get("alarm_enabled", False) for r in cfg2.get("rules", {}).values()),
        no_alarm3_configured=not any(r.get("alarm_enabled", False) for r in cfg3.get("rules", {}).values()),
        queue_warn_threshold=config.QUEUE_WARNING_THRESHOLD,
        queue_crit_threshold=config.QUEUE_CRITICAL_THRESHOLD,
        throughput_filters=throughput_filters,
    )


def flows_page() -> str:
    """Render the Flows page with per-container metrics and alarm status overlay."""
    status = get_cached_status()
    container_metrics = cache.cached_nowait(
        "flows",
        get_container_apps_metrics,
        ttl=config.API_CACHE_TTL,
    )
    return render_template(
        "flows.html",
        status=status,
        container_metrics=container_metrics,
        alarm_map=build_alarm_map(),
        refresh_interval=config.API_CACHE_TTL,
        data_is_stale=cache.is_cache_stale("status"),
    )


def exceptions_page() -> str:
    """Render the Exceptions page, filtered to the requested time window (default 24 h)."""
    hours_raw = request.args.get("hours", "24", type=str)
    allowed = {"1": 1, "6": 6, "12": 12, "24": 24, "48": 48, "72": 72}
    hours = allowed.get(hours_raw, 24)
    exceptions = cache.cached_nowait(
        f"exceptions_{hours}",
        lambda: get_exceptions(hours=hours),
        ttl=config.API_CACHE_TTL,
    )
    return render_template(
        "exceptions.html",
        exceptions=exceptions,
        hours=hours,
        config_ok=bool(config.AZURE_LOG_ANALYTICS_WORKSPACE_ID),
        data_is_stale=cache.is_cache_stale(f"exceptions_{hours}"),
    )


def service_bus_page() -> str:
    """Render the Service Bus page showing queue depths and dead-letter counts."""
    cached_sb = cache.cached_nowait(
        "servicebus",
        lambda: {"queues": get_queues()},
        ttl=config.API_CACHE_TTL,
    )
    queues = cached_sb["queues"]
    flows = build_flow_data(queues)
    return render_template(
        "service_bus.html",
        queues=queues,
        flows=flows,
        data_is_stale=cache.is_cache_stale("servicebus"),
    )


def messages_page() -> str:
    """Render the Messages page, optionally filtered to a specific Service Bus queue."""
    queue_filter = request.args.get("queue", "").strip()
    flow_label = None
    microservice_ids: list[str] | None = None

    if queue_filter:
        microservice_ids = queue_to_microservice_ids(queue_filter)
        if not microservice_ids:
            microservice_ids = ["__no_match__"]
        workflow_id = queue_to_workflow_id(queue_filter)
        if workflow_id:
            flows = get_flows()
            flow_label = flows.get(workflow_id, {}).get("label", workflow_id)

    # Vary the cache key by queue_filter: the builder's result depends on
    # microservice_ids, so a fixed "messages" key would serve one filter's
    # cached data to a different filter.
    cache_key = f"messages_{queue_filter}" if queue_filter else "messages"
    messages = cache.cached_nowait(
        cache_key,
        lambda: get_messages_today(microservice_ids=microservice_ids),
        ttl=config.API_CACHE_TTL,
    )
    cached_sb = cache.cached_nowait("servicebus", lambda: {"queues": get_queues()}, ttl=config.API_CACHE_TTL)
    queue_names = sorted(q["name"] for q in cached_sb.get("queues", []) if q.get("name"))
    return render_template(
        "messages.html",
        messages=messages,
        config_ok=bool(config.AZURE_LOG_ANALYTICS_WORKSPACE_ID),
        queue_filter=queue_filter,
        flow_label=flow_label,
        queue_names=queue_names,
        data_is_stale=cache.is_cache_stale(cache_key),
    )


def trace_page(operation_id: str) -> str | tuple[str, int]:
    """Render the distributed trace view for a given Application Insights operation ID."""
    trace_data = get_trace(operation_id)
    if not trace_data["ok"]:
        return render_template("trace.html", operation_id=operation_id, trace_data=trace_data), 404
    return render_template("trace.html", operation_id=operation_id, trace_data=trace_data)


def register(app: Flask) -> None:
    """Register every page route onto ``app`` with its original flat endpoint name."""
    app.add_url_rule("/set-language", endpoint="set_language", view_func=set_language, methods=["POST"])
    app.add_url_rule("/", endpoint="index", view_func=index)
    app.add_url_rule("/flows", endpoint="flows_page", view_func=flows_page)
    app.add_url_rule("/exceptions", endpoint="exceptions_page", view_func=exceptions_page)
    app.add_url_rule("/service-bus", endpoint="service_bus_page", view_func=service_bus_page)
    app.add_url_rule("/messages", endpoint="messages_page", view_func=messages_page)
    app.add_url_rule("/trace/<operation_id>", endpoint="trace_page", view_func=trace_page)
