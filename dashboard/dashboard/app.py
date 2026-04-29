"""
Integration Hub Dashboard — Flask application entry point.
"""
from __future__ import annotations

import logging
import os
import ssl
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Callable

from flask import Flask, Response, jsonify, render_template, request

from dashboard import config
from dashboard.services.alarms import (
    generate_rule_id as generate_alarm1_rule_id,
    get_alarm_status,
    get_config_page_data,
    load_alarm_config,
    save_alarm_config,
)
from dashboard.services.alarm2 import (
    generate_rule_id,
    get_alarm2_config_page_data,
    get_alarm2_status,
    load_alarm2_config,
    save_alarm2_config,
)
from dashboard.services.alarm3 import (
    generate_rule_id as generate_alarm3_rule_id,
    get_alarm3_config_page_data,
    get_alarm3_status,
    load_alarm3_config,
    save_alarm3_config,
)
from dashboard.services.arm import discover_flows, queue_to_microservice_ids
from dashboard.services.azure_monitor import get_exceptions, get_messages_today
from dashboard.services.container_apps import get_container_apps_metrics
from dashboard.services.flows import build_flow_data, get_active_flows, get_flows, overall_health, queue_to_workflow_id
from dashboard.services.service_bus import get_message_metrics, get_queues
from dashboard.services.traces import get_trace


def _read_extra_ca_file(cert_path: Path) -> str | None:
    """Read a PEM or DER certificate file and return PEM text."""
    try:
        raw = cert_path.read_bytes()
    except OSError:
        return None

    if raw.startswith(b"-----BEGIN CERTIFICATE-----"):
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return None

    try:
        return ssl.DER_cert_to_PEM_cert(raw)
    except ValueError:
        return None

def _configure_ssl_trust() -> None:
    """Build an OpenSSL-compatible CA bundle that works behind corporate TLS interception.

    Combines the certifi default bundle with the corporate CA certificate
    specified in AZURE_CA_CERT_FILE.  The resulting bundle is written to a
    temp file and both SSL_CERT_FILE and REQUESTS_CA_BUNDLE are pointed at it
    so that all Python HTTP clients (requests, httpx, urllib3, Azure SDK) use
    the combined trust store.
    """
    if os.name != "nt":
        return

    bundle_path = Path(tempfile.gettempdir()) / "integration-hub-dashboard-ca.pem"

    # Only read the explicit corporate CA env var — REQUESTS_CA_BUNDLE and
    # SSL_CERT_FILE may contain stale system-level values that aren't valid
    # PEM bundles (e.g. C:\Certs\portal.azure.com).
    extra_ca = os.environ.get("AZURE_CA_CERT_FILE")

    try:
        import certifi  # noqa: PLC0415

        bundle_parts = [Path(certifi.where()).read_text(encoding="utf-8")]
        if extra_ca:
            extra_pem = _read_extra_ca_file(Path(extra_ca))
            if extra_pem:
                bundle_parts.append(extra_pem)

        # Always write the bundle — even if there's no extra cert, we need a
        # valid file to override the potentially-broken system SSL_CERT_FILE.
        bundle_path.write_text("\n".join(bundle_parts) + "\n", encoding="utf-8")
        os.environ["SSL_CERT_FILE"] = str(bundle_path)
        os.environ["REQUESTS_CA_BUNDLE"] = str(bundle_path)
        return
    except Exception as exc:
        log.warning("certifi-based CA bundle failed: %s", exc)

    # Fallback: build from Windows certificate store
    certs: dict[bytes, None] = {}
    for store_name in ("ROOT", "CA"):
        for cert_bytes, encoding, _trust in ssl.enum_certificates(store_name):  # type: ignore[attr-defined]
            if encoding == "x509_asn":
                certs[cert_bytes] = None

    if not certs:
        return

    pem_data = "".join(ssl.DER_cert_to_PEM_cert(cert) for cert in certs)
    bundle_path.write_text(pem_data, encoding="ascii")

    os.environ["SSL_CERT_FILE"] = str(bundle_path)
    os.environ["REQUESTS_CA_BUNDLE"] = str(bundle_path)


_configure_ssl_trust()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
log = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = config.FLASK_SECRET_KEY

# ---------------------------------------------------------------------------
# Simple in-memory cache for /api/status
# ---------------------------------------------------------------------------

_cache_lock = Lock()
_cache_data: dict = {
    "status":     {"data": None, "ts": 0.0},
    "flows":      {"data": None, "ts": 0.0},
    "exceptions": {"data": None, "ts": 0.0},
    "servicebus": {"data": None, "ts": 0.0},
    "messages":   {"data": None, "ts": 0.0},
    "alarms":     {"data": None, "ts": 0.0},
    "alarm2":     {"data": None, "ts": 0.0},
    "alarm3":     {"data": None, "ts": 0.0},
}


def _cached(key: str, builder: Callable[[], Any], ttl: float | None = None, force: bool = False) -> Any:
    """Generic TTL cache helper. Returns cached value or calls builder() to refresh.

    The lock is held only for the fast cache-check and the final store — never
    during the (potentially slow) Azure API call, so concurrent requests are not
    blocked waiting for a cache rebuild.
    """
    _ttl = ttl if ttl is not None else config.API_CACHE_TTL
    now = time.monotonic()

    # Fast path: return stale-check under lock, return immediately if fresh
    if not force:
        with _cache_lock:
            entry = _cache_data.setdefault(key, {"data": None, "ts": 0.0})
            if (now - entry["ts"]) <= _ttl and entry["data"] is not None:
                return entry["data"]

    # Slow path: call builder outside the lock so other requests aren't blocked
    new_data = builder()

    with _cache_lock:
        _cache_data[key]["data"] = new_data
        _cache_data[key]["ts"] = time.monotonic()

    return new_data


_bg_refresh_in_flight: set[str] = set()
_bg_refresh_lock = Lock()


def _cached_nowait(key: str, builder: Callable[[], Any], ttl: float | None = None) -> Any:
    """Stale-while-revalidate: return cached data immediately (even if stale)
    and trigger a background refresh if the entry is expired.  Only blocks on
    the very first call when there is no cached value at all.
    """
    _ttl = ttl if ttl is not None else config.API_CACHE_TTL
    now = time.monotonic()

    with _cache_lock:
        entry = _cache_data.setdefault(key, {"data": None, "ts": 0.0})
        cached = entry["data"]
        is_stale = (now - entry["ts"]) > _ttl

    if cached is None:
        # No data yet — must block once so the page has something to render.
        return _cached(key, builder, ttl=ttl)

    if is_stale:
        # Serve stale data immediately; refresh in a background thread.
        with _bg_refresh_lock:
            if key not in _bg_refresh_in_flight:
                _bg_refresh_in_flight.add(key)

                def _refresh(k: str, b: Callable[[], Any], t: float) -> None:
                    try:
                        _cached(k, b, ttl=t, force=True)
                    except Exception as exc:  # noqa: BLE001
                        log.warning("Background cache refresh failed for %r: %s", k, exc)
                    finally:
                        with _bg_refresh_lock:
                            _bg_refresh_in_flight.discard(k)

                threading.Thread(target=_refresh, args=(key, builder, _ttl), daemon=True).start()

    return cached


def _multi_cached_nowait(
    items: list[tuple[str, Callable[[], Any], float | None]],
) -> list[Any]:
    """Stale-while-revalidate for **multiple** cache keys simultaneously.

    * Hot entries  → returned instantly (no I/O).
    * Stale entries → served immediately; background thread refreshes each one.
    * Cold entries  → fetched **in parallel** via a thread pool, then returned.

    This replaces sequential ``_cached_nowait`` calls on the overview page so
    that Azure Log Analytics queries for all three alarms run concurrently
    instead of one-after-the-other.
    """
    _ttl_default = config.API_CACHE_TTL
    now = time.monotonic()

    resolved: dict[str, Any] = {}
    cold: list[tuple[str, Callable[[], Any], float]] = []

    for key, builder, ttl in items:
        _ttl = ttl if ttl is not None else _ttl_default
        with _cache_lock:
            entry = _cache_data.setdefault(key, {"data": None, "ts": 0.0})
            cached = entry["data"]
            is_stale = (now - entry["ts"]) > _ttl

        if cached is None:
            cold.append((key, builder, _ttl))
        else:
            resolved[key] = cached
            if is_stale:
                with _bg_refresh_lock:
                    if key not in _bg_refresh_in_flight:
                        _bg_refresh_in_flight.add(key)

                        def _refresh(k: str, b: Callable[[], Any], t: float) -> None:
                            try:
                                _cached(k, b, ttl=t, force=True)
                            except Exception as exc:  # noqa: BLE001
                                log.warning("Background cache refresh failed for %r: %s", k, exc)
                            finally:
                                with _bg_refresh_lock:
                                    _bg_refresh_in_flight.discard(k)

                        threading.Thread(
                            target=_refresh, args=(key, builder, _ttl), daemon=True
                        ).start()

    if cold:
        # Fetch all cold entries concurrently — one thread per entry.
        with ThreadPoolExecutor(max_workers=len(cold)) as pool:
            futures = {pool.submit(_cached, k, b, t, True): k for k, b, t in cold}
            for future in as_completed(futures):
                k = futures[future]
                try:
                    resolved[k] = future.result()
                except Exception as exc:  # noqa: BLE001
                    log.warning("Parallel cold fetch failed for %r: %s", k, exc)
                    resolved[k] = []

    return [resolved.get(key, []) for key, _, _ in items]


def _get_cached_status(force: bool = False) -> dict:
    if force:
        return _cached("status", _build_status, force=True)
    return _cached_nowait("status", _build_status)


def _is_cache_stale(key: str, ttl: float | None = None) -> bool:
    """Return True if the cache entry for *key* is expired (or was never populated)."""
    _ttl = ttl if ttl is not None else config.API_CACHE_TTL
    with _cache_lock:
        entry = _cache_data.get(key, {"data": None, "ts": 0.0})
        if entry["data"] is None:
            return False  # first-load blocking fetch; not stale, just cold
        return (time.monotonic() - entry["ts"]) > _ttl


def _build_status() -> dict:
    queues = get_queues()
    active_flows = get_active_flows()
    flows = build_flow_data(queues, active_flows)

    total_active = sum(q.get("active_message_count", 0) for q in queues)
    total_dlq = sum(q.get("dead_letter_message_count", 0) for q in queues)

    exceptions_1h = get_exceptions(hours=1)
    exception_count = len(exceptions_1h)

    flow_statuses = [f["health"] for f in flows]
    sys_health = overall_health(flow_statuses)
    healthy_count = flow_statuses.count("healthy")
    warning_count = flow_statuses.count("warning")
    critical_count = flow_statuses.count("critical")

    return {
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
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
    }


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@app.route("/")
def index() -> str:
    status = _get_cached_status()
    return render_template(
        "index.html",
        status=status,
        refresh_interval=config.API_CACHE_TTL,
        data_is_stale=_is_cache_stale("status"),
    )


@app.route("/flows")
def flows_page() -> str:
    status = _get_cached_status()
    container_metrics = _cached_nowait(
        "flows",
        get_container_apps_metrics,
        ttl=config.API_CACHE_TTL,
    )
    return render_template(
        "flows.html",
        status=status,
        container_metrics=container_metrics,
        refresh_interval=config.API_CACHE_TTL,
        data_is_stale=_is_cache_stale("status"),
    )


@app.route("/exceptions")
def exceptions_page() -> str:
    hours = int(request.args.get("hours", 24))
    exceptions = _cached_nowait(
        f"exceptions_{hours}",
        lambda: get_exceptions(hours=hours),
        ttl=config.API_CACHE_TTL,
    )
    return render_template(
        "exceptions.html",
        exceptions=exceptions,
        hours=hours,
        config_ok=bool(config.AZURE_LOG_ANALYTICS_WORKSPACE_ID),
        data_is_stale=_is_cache_stale(f"exceptions_{hours}"),
    )


@app.route("/service-bus")
def service_bus_page() -> str:
    cached_sb = _cached_nowait(
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
        data_is_stale=_is_cache_stale("servicebus"),
    )


@app.route("/messages")
def messages_page() -> str:
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

    messages = _cached_nowait(
        "messages",
        lambda: get_messages_today(microservice_ids=microservice_ids),
        ttl=config.API_CACHE_TTL,
    )
    cached_sb = _cached_nowait("servicebus", lambda: {"queues": get_queues()}, ttl=config.API_CACHE_TTL)
    queue_names = sorted(q["name"] for q in cached_sb.get("queues", []) if q.get("name"))
    return render_template(
        "messages.html",
        messages=messages,
        config_ok=bool(config.AZURE_LOG_ANALYTICS_WORKSPACE_ID),
        queue_filter=queue_filter,
        flow_label=flow_label,
        queue_names=queue_names,
        data_is_stale=_is_cache_stale("messages"),
    )


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.route("/trace/<operation_id>")
def trace_page(operation_id: str) -> str | tuple[str, int]:
    trace_data = get_trace(operation_id)
    if not trace_data["ok"]:
        return render_template("trace.html", operation_id=operation_id, trace_data=trace_data), 404
    return render_template("trace.html", operation_id=operation_id, trace_data=trace_data)


@app.route("/api/status")
def api_status() -> Response:
    force = request.args.get("force", "false").lower() == "true"
    data = _get_cached_status(force=force)
    return jsonify(data)


@app.route("/api/refresh")
def api_refresh() -> Response:
    """Force-refresh all caches including ARM flow discovery."""
    discover_flows(force=True)
    # Bust every cache entry
    with _cache_lock:
        for entry in _cache_data.values():
            entry["ts"] = 0.0
    data = _get_cached_status(force=True)
    return jsonify({"refreshed": True, "active_flows": list(get_active_flows().keys()), **data})


@app.route("/api/flows")
def api_flows() -> Response:
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


@app.route("/api/messages")
def api_messages() -> Response:
    messages = get_messages_today()
    return jsonify({"messages": messages, "count": len(messages)})


@app.route("/api/servicebus-metrics")
def api_servicebus_metrics() -> Response:
    hours = request.args.get("hours", "1", type=str)
    allowed = {"1": 1, "6": 6, "12": 12, "24": 24, "168": 168, "720": 720}
    timespan_hours = allowed.get(hours, 1)
    queue = request.args.get("queue", "").strip() or None
    metrics = get_message_metrics(timespan_hours, queue_name=queue)
    return jsonify(metrics)


# ---------------------------------------------------------------------------
# Alarm page routes
# ---------------------------------------------------------------------------

@app.route("/api/alarms/status")
def api_alarms_status() -> Response:
    """JSON endpoint returning all three alarm statuses in parallel.

    Supports ``?refresh=1`` to force a cache bust.  Useful for async page
    loading or periodic polling from the browser.
    """
    force = request.args.get("refresh") == "1"
    if force:
        with _cache_lock:
            _cache_data["alarms"]["ts"] = 0.0
            _cache_data["alarm2"]["ts"] = 0.0
            _cache_data["alarm3"]["ts"] = 0.0

    alarm1_rows, alarm2_rows, alarm3_rows = _multi_cached_nowait([
        ("alarms", get_alarm_status,  config.API_CACHE_TTL),
        ("alarm2", get_alarm2_status, config.API_CACHE_TTL),
        ("alarm3", get_alarm3_status, config.API_CACHE_TTL),
    ])
    return jsonify({
        "alarm1": alarm1_rows,
        "alarm2": alarm2_rows,
        "alarm3": alarm3_rows,
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
        "poll_interval_seconds": int(config.API_CACHE_TTL),
    })


@app.route("/alarms")
def alarms_overview_page() -> str:
    if request.args.get("refresh") == "1":
        with _cache_lock:
            _cache_data["alarms"]["ts"] = 0.0
            _cache_data["alarm2"]["ts"] = 0.0
            _cache_data["alarm3"]["ts"] = 0.0

    # Fetch all three alarm statuses concurrently — cold fetches run in
    # parallel threads instead of blocking sequentially.
    alarm1_rows, alarm2_rows, alarm3_rows = _multi_cached_nowait([
        ("alarms", get_alarm_status,  config.API_CACHE_TTL),
        ("alarm2", get_alarm2_status, config.API_CACHE_TTL),
        ("alarm3", get_alarm3_status, config.API_CACHE_TTL),
    ])

    cfg1 = load_alarm_config()
    any_alarm1 = any(s.get("alarm_enabled", False) for s in cfg1.get("rules", {}).values())
    cfg2 = load_alarm2_config()
    any_alarm2 = any(r.get("alarm_enabled", False) for r in cfg2.get("rules", {}).values())
    cfg3 = load_alarm3_config()
    any_alarm3 = any(r.get("alarm_enabled", False) for r in cfg3.get("rules", {}).values())
    return render_template(
        "alarms_overview.html",
        alarm1_rows=alarm1_rows,
        no_alarm1_configured=not any_alarm1,
        alarm2_rows=alarm2_rows,
        no_alarm2_configured=not any_alarm2,
        alarm3_rows=alarm3_rows,
        no_alarm3_configured=not any_alarm3,
        config_ok=bool(config.AZURE_LOG_ANALYTICS_WORKSPACE_ID),
        refreshed_at=datetime.now(timezone.utc).strftime("%d %b %Y  %H:%M:%S UTC"),
        refresh_interval=int(config.API_CACHE_TTL),
    )


@app.route("/alarms/inactivity")
def alarm_page() -> str:
    alarm_rows = _cached_nowait(
        "alarms",
        get_alarm_status,
        ttl=config.API_CACHE_TTL,
    )
    # Determine whether any alarms have been configured at all
    cfg = load_alarm_config()
    any_configured = any(
        s.get("alarm_enabled", False) for s in cfg.get("rules", {}).values()
    )
    return render_template(
        "alarm.html",
        alarm_rows=alarm_rows,
        no_alarms_configured=not any_configured,
        config_ok=bool(config.AZURE_LOG_ANALYTICS_WORKSPACE_ID),
        refreshed_at=datetime.now(timezone.utc).strftime("%d %b %Y  %H:%M:%S UTC"),
        data_is_stale=_is_cache_stale("alarms"),
    )


@app.route("/alarm-config", methods=["GET", "POST"])
def alarm_config_page() -> str:
    saved = False

    if request.method == "POST":
        cfg = load_alarm_config()
        rules_cfg = cfg.setdefault("rules", {})

        def _int(field: str, default: int) -> int:
            try:
                return max(1, int(request.form.get(field, default)))
            except (ValueError, TypeError):
                return default

        # Handle deletions
        for key in list(request.form):
            if key.startswith("delete_"):
                rid = key[len("delete_"):]
                rules_cfg.setdefault(rid, {})["deleted"] = True

        # Update existing rules
        submitted_ids = [
            key[len("alerting_gap_"):]
            for key in request.form
            if key.startswith("alerting_gap_")
        ]
        for rid in submitted_ids:
            if rules_cfg.get(rid, {}).get("deleted"):
                continue
            entry = rules_cfg.setdefault(rid, {})
            entry["alarm_enabled"]             = f"enabled_{rid}" in request.form
            entry["email_alerts_enabled"]      = f"email_{rid}" in request.form
            entry["display_name"]              = (request.form.get(f"display_name_{rid}") or "").strip()
            entry["workflow_id"]               = (request.form.get(f"workflow_id_{rid}") or "").strip()
            entry["alerting_gap_minutes"]      = _int(f"alerting_gap_{rid}", 60)
            entry["day_threshold_minutes"]     = _int(f"day_threshold_{rid}", 60)
            entry["evening_threshold_minutes"] = _int(f"evening_threshold_{rid}", 120)
            entry["weekend_threshold_minutes"] = _int(f"weekend_threshold_{rid}", 240)

        # Add new rule
        new_wid = (request.form.get("new_workflow_id") or "").strip()
        if new_wid:
            new_rid = generate_alarm1_rule_id(new_wid, set(rules_cfg))
            rules_cfg[new_rid] = {
                "display_name":              (request.form.get("new_display_name") or "").strip(),
                "alarm_enabled":             False,
                "workflow_id":               new_wid,
                "day_threshold_minutes":     _int("new_day_threshold", 60),
                "evening_threshold_minutes": _int("new_evening_threshold", 120),
                "weekend_threshold_minutes": _int("new_weekend_threshold", 240),
                "alerting_gap_minutes":      _int("new_alerting_gap", 60),
                "email_alerts_enabled":      False,
            }

        save_alarm_config(cfg)
        with _cache_lock:
            _cache_data["alarms"]["ts"] = 0.0
        saved = True

    rules = get_config_page_data()
    return render_template(
        "alarm_config.html",
        rules=rules,
        saved=saved,
        config_ok=bool(config.AZURE_LOG_ANALYTICS_WORKSPACE_ID),
        smtp_configured=bool(config.ALERT_EMAIL_ENABLED and config.ACS_CONNECTION_STRING and config.ALERT_EMAIL_TO),
    )


@app.route("/alarms/outgoing-messages")
def alarm2_page() -> str:
    alarm2_rows = _cached_nowait(
        "alarm2",
        get_alarm2_status,
        ttl=config.API_CACHE_TTL,
    )
    cfg = load_alarm2_config()
    any_configured = any(
        r.get("alarm_enabled", False) for r in cfg.get("rules", {}).values()
    )
    return render_template(
        "alarm2.html",
        alarm2_rows=alarm2_rows,
        no_alarms_configured=not any_configured,
        config_ok=bool(config.AZURE_LOG_ANALYTICS_WORKSPACE_ID),
        refreshed_at=datetime.now(timezone.utc).strftime("%d %b %Y  %H:%M:%S UTC"),
        data_is_stale=_is_cache_stale("alarm2"),
    )


@app.route("/alarm2-config", methods=["GET", "POST"])
def alarm2_config_page() -> str:
    saved = False

    if request.method == "POST":
        cfg = load_alarm2_config()
        rules_cfg = cfg.setdefault("rules", {})

        def _int(field: str, default: int, minimum: int = 0) -> int:
            try:
                return max(minimum, int(request.form.get(field, default)))
            except (ValueError, TypeError):
                return default

        # --- Handle deletions first ---
        for key in list(request.form):
            if key.startswith("delete_"):
                rid = key[len("delete_"):]
                rules_cfg.setdefault(rid, {})["deleted"] = True

        # --- Update existing rules (skip deleted) ---
        submitted_ids = [
            key[len("alerting_gap_"):]
            for key in request.form
            if key.startswith("alerting_gap_")
        ]
        for rid in submitted_ids:
            if rules_cfg.get(rid, {}).get("deleted"):
                continue
            entry = rules_cfg.setdefault(rid, {})
            entry["alarm_enabled"]           = f"enabled_{rid}" in request.form
            entry["email_alerts_enabled"]    = f"email_{rid}" in request.form
            entry["display_name"]            = (request.form.get(f"display_name_{rid}") or "").strip()
            entry["health_board"]            = (request.form.get(f"health_board_{rid}") or "").strip()
            entry["peer_service"]            = (request.form.get(f"peer_service_{rid}") or "").strip()
            entry["window_duration_minutes"] = _int(f"window_duration_{rid}", 2880, minimum=1)
            entry["threshold"]               = _int(f"threshold_{rid}", 0, minimum=0)
            entry["alerting_gap_minutes"]    = _int(f"alerting_gap_{rid}", 60, minimum=1)

        # --- Add new rule if submitted ---
        new_hb = (request.form.get("new_health_board") or "").strip()
        new_ps = (request.form.get("new_peer_service") or "").strip()
        if new_hb and new_ps:
            new_id = generate_rule_id(new_hb, new_ps, set(rules_cfg))
            rules_cfg[new_id] = {
                "display_name":            (request.form.get("new_display_name") or "").strip()
                                           or f"{new_hb} → {new_ps}",
                "alarm_enabled":           False,
                "health_board":            new_hb,
                "peer_service":            new_ps,
                "window_duration_minutes": _int("new_window_duration", 2880, minimum=1),
                "threshold":               _int("new_threshold", 0, minimum=0),
                "alerting_gap_minutes":    _int("new_alerting_gap", 60, minimum=1),
                "email_alerts_enabled":    False,
            }

        save_alarm2_config(cfg)
        with _cache_lock:
            _cache_data["alarm2"]["ts"] = 0.0
        saved = True

    rules = get_alarm2_config_page_data()
    return render_template(
        "alarm2_config.html",
        rules=rules,
        saved=saved,
        config_ok=bool(config.AZURE_LOG_ANALYTICS_WORKSPACE_ID),
        smtp_configured=bool(config.ALERT_EMAIL_ENABLED and config.ACS_CONNECTION_STRING and config.ALERT_EMAIL_TO),
    )


@app.route("/alarms/failures")
def alarm3_page() -> str:
    alarm3_rows = _cached_nowait(
        "alarm3",
        get_alarm3_status,
        ttl=config.API_CACHE_TTL,
    )
    cfg = load_alarm3_config()
    any_configured = any(
        r.get("alarm_enabled", False) for r in cfg.get("rules", {}).values()
    )
    return render_template(
        "alarm3.html",
        alarm3_rows=alarm3_rows,
        no_alarms_configured=not any_configured,
        config_ok=bool(config.AZURE_LOG_ANALYTICS_WORKSPACE_ID),
        refreshed_at=datetime.now(timezone.utc).strftime("%d %b %Y  %H:%M:%S UTC"),
        data_is_stale=_is_cache_stale("alarm3"),
    )


@app.route("/alarm3-config", methods=["GET", "POST"])
def alarm3_config_page() -> str:
    saved = False

    if request.method == "POST":
        cfg = load_alarm3_config()
        rules_cfg = cfg.setdefault("rules", {})

        def _int(field: str, default: int, minimum: int = 0) -> int:
            try:
                return max(minimum, int(request.form.get(field, default)))
            except (ValueError, TypeError):
                return default

        for key in list(request.form):
            if key.startswith("delete_"):
                rid = key[len("delete_"):]
                rules_cfg.setdefault(rid, {})["deleted"] = True

        submitted_ids = [
            key[len("alerting_gap_"):]
            for key in request.form
            if key.startswith("alerting_gap_")
        ]
        for rid in submitted_ids:
            if rules_cfg.get(rid, {}).get("deleted"):
                continue
            entry = rules_cfg.setdefault(rid, {})
            entry["alarm_enabled"]           = f"enabled_{rid}" in request.form
            entry["email_alerts_enabled"]    = f"email_{rid}" in request.form
            entry["display_name"]            = (request.form.get(f"display_name_{rid}") or "").strip()
            entry["workflow_id"]             = (request.form.get(f"workflow_id_{rid}") or "").strip()
            entry["window_duration_minutes"] = _int(f"window_duration_{rid}", 15, minimum=1)
            entry["threshold"]               = _int(f"threshold_{rid}", 1, minimum=1)
            entry["alerting_gap_minutes"]    = _int(f"alerting_gap_{rid}", 60, minimum=1)

        new_wid = (request.form.get("new_workflow_id") or "").strip()
        if new_wid:
            new_id = generate_alarm3_rule_id(new_wid, set(rules_cfg))
            rules_cfg[new_id] = {
                "display_name":            (request.form.get("new_display_name") or "").strip()
                                           or f"{new_wid} Failures",
                "alarm_enabled":           False,
                "workflow_id":             new_wid,
                "window_duration_minutes": _int("new_window_duration", 15, minimum=1),
                "threshold":               _int("new_threshold", 1, minimum=1),
                "alerting_gap_minutes":    _int("new_alerting_gap", 60, minimum=1),
                "email_alerts_enabled":    False,
            }

        save_alarm3_config(cfg)
        with _cache_lock:
            _cache_data["alarm3"]["ts"] = 0.0
        saved = True

    rules = get_alarm3_config_page_data()
    return render_template(
        "alarm3_config.html",
        rules=rules,
        saved=saved,
        config_ok=bool(config.AZURE_LOG_ANALYTICS_WORKSPACE_ID),
        smtp_configured=bool(config.ALERT_EMAIL_ENABLED and config.ACS_CONNECTION_STRING and config.ALERT_EMAIL_TO),
    )


@app.template_filter("format_bytes")
def format_bytes(size: int | float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size = size / 1024
    return f"{size:.1f} TB"


@app.template_filter("health_badge")
def health_badge(health: str) -> str:
    colours = {
        "healthy": "success",
        "warning": "warning",
        "critical": "danger",
        "unknown": "secondary",
    }
    return colours.get(health, "secondary")


if __name__ == "__main__":
    app.run(debug=config.FLASK_DEBUG, host="0.0.0.0", port=5000)  # nosec B104
