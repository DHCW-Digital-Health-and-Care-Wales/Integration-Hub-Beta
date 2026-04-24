"""
Integration Hub Dashboard — Flask application entry point.
"""
from __future__ import annotations

import logging
import os
import ssl
import tempfile
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from threading import Lock

from flask import Flask, jsonify, render_template, request

from dashboard import config
from dashboard.services.azure_monitor import get_exceptions, get_messages_today
from dashboard.services.container_apps import get_container_apps_metrics
from dashboard.services.flows import build_flow_data, get_active_flows, get_flows, overall_health
from dashboard.services.service_bus import get_queues, get_message_metrics


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
    """Build an OpenSSL-compatible CA bundle that works behind corporate TLS interception."""
    if os.name != "nt":
        return

    bundle_path = Path(tempfile.gettempdir()) / "integration-hub-dashboard-ca.pem"

    extra_cert_paths = []
    for env_name in ("AZURE_CA_CERT_FILE", "REQUESTS_CA_BUNDLE", "SSL_CERT_FILE"):
        env_value = os.environ.get(env_name)
        if env_value:
            extra_cert_paths.append(Path(env_value))

    try:
        import certifi

        bundle_parts = [Path(certifi.where()).read_text(encoding="utf-8")]
        for cert_path in extra_cert_paths:
            extra_pem = _read_extra_ca_file(cert_path)
            if extra_pem:
                bundle_parts.append(extra_pem)

        if len(bundle_parts) > 1:
            bundle_path.write_text("\n".join(bundle_parts) + "\n", encoding="utf-8")
            os.environ["SSL_CERT_FILE"] = str(bundle_path)
            os.environ["REQUESTS_CA_BUNDLE"] = str(bundle_path)
            return
    except Exception:
        pass

    certs: dict[bytes, None] = {}
    for store_name in ("ROOT", "CA"):
        for cert_bytes, encoding, _trust in ssl.enum_certificates(store_name):
            if encoding == "x509_asn":
                certs[cert_bytes] = None

    if not certs:
        return

    if not bundle_path.is_file():
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
_cache_data: dict = {"status": {}, "timestamp": 0.0}


def _get_cached_status(force: bool = False) -> dict:
    now = time.monotonic()
    with _cache_lock:
        if force or (now - _cache_data["timestamp"]) > config.API_CACHE_TTL:
            _cache_data["status"] = _build_status()
            _cache_data["timestamp"] = now
    return _cache_data["status"]


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
    }


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    status = _get_cached_status()
    return render_template(
        "index.html",
        status=status,
        refresh_interval=config.API_CACHE_TTL,
    )


@app.route("/flows")
def flows_page():
    status = _get_cached_status()
    container_metrics = get_container_apps_metrics()
    active_flows = get_active_flows()
    return render_template(
        "flows.html",
        status=status,
        container_metrics=container_metrics,
        flows_def=active_flows,
        refresh_interval=config.API_CACHE_TTL,
    )


@app.route("/exceptions")
def exceptions_page():
    hours = int(request.args.get("hours", 24))
    exceptions = get_exceptions(hours=hours)
    return render_template(
        "exceptions.html",
        exceptions=exceptions,
        hours=hours,
        config_ok=bool(config.AZURE_LOG_ANALYTICS_WORKSPACE_ID),
    )


@app.route("/service-bus")
def service_bus_page():
    queues = get_queues()
    flows = build_flow_data(queues)
    return render_template(
        "service_bus.html",
        queues=queues,
        flows=flows,
    )


@app.route("/messages")
def messages_page():
    queue_filter = request.args.get("queue", "").strip()
    flow_label = None
    microservice_ids: list[str] | None = None

    if queue_filter:
        from dashboard.services.arm import queue_to_microservice_ids
        from dashboard.services.flows import queue_to_workflow_id, get_flows

        microservice_ids = queue_to_microservice_ids(queue_filter)
        if not microservice_ids:
            # Queue exists but no Container App uses it — show empty results
            microservice_ids = ["__no_match__"]
        workflow_id = queue_to_workflow_id(queue_filter)
        if workflow_id:
            flows = get_flows()
            flow_label = flows.get(workflow_id, {}).get("label", workflow_id)

    messages = get_messages_today(microservice_ids=microservice_ids)
    return render_template(
        "messages.html",
        messages=messages,
        config_ok=bool(config.AZURE_LOG_ANALYTICS_WORKSPACE_ID),
        queue_filter=queue_filter,
        flow_label=flow_label,
    )


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.route("/api/status")
def api_status():
    force = request.args.get("force", "false").lower() == "true"
    data = _get_cached_status(force=force)
    return jsonify(data)


@app.route("/api/refresh")
def api_refresh():
    """Force-refresh both the status cache and the ARM flow discovery cache."""
    from dashboard.services.arm import get_deployed_flow_ids
    get_deployed_flow_ids(force=True)
    data = _get_cached_status(force=True)
    return jsonify({"refreshed": True, "active_flows": list(get_active_flows().keys()), **data})


@app.route("/api/flows")
def api_flows():
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
def api_messages():
    messages = get_messages_today()
    return jsonify({"messages": messages, "count": len(messages)})


@app.route("/api/servicebus-metrics")
def api_servicebus_metrics():
    hours = request.args.get("hours", "1", type=str)
    allowed = {"1": 1, "6": 6, "12": 12, "24": 24, "168": 168, "720": 720}
    timespan_hours = allowed.get(hours, 1)
    queue = request.args.get("queue", "").strip() or None
    metrics = get_message_metrics(timespan_hours, queue_name=queue)
    return jsonify(metrics)


# ---------------------------------------------------------------------------
# Template helpers
# ---------------------------------------------------------------------------

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
    app.run(debug=config.FLASK_DEBUG, host="0.0.0.0", port=5000)
