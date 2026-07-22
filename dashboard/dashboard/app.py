"""
Integration Hub Dashboard — Flask application entry point.
"""

from __future__ import annotations

import logging
import os
import ssl
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import Flask, Response, jsonify, render_template, request, session
from flask_babel import Babel  # type: ignore[import-untyped]

import dashboard.config as config
from dashboard.routes import api as api_routes
from dashboard.routes import pages as pages_routes
from dashboard.services import cache
from dashboard.services.alarm1 import (
    generate_rule_id as generate_alarm1_rule_id,
)
from dashboard.services.alarm1 import (
    get_alarm_status,
    get_config_page_data,
    load_alarm_config,
    pause_alarm_rule,
    save_alarm_config,
    unpause_alarm_rule,
)
from dashboard.services.alarm2 import (
    generate_rule_id,
    get_alarm2_config_page_data,
    get_alarm2_status,
    load_alarm2_config,
    pause_alarm2_rule,
    save_alarm2_config,
    unpause_alarm2_rule,
)
from dashboard.services.alarm3 import (
    generate_rule_id as generate_alarm3_rule_id,
)
from dashboard.services.alarm3 import (
    get_alarm3_config_page_data,
    get_alarm3_status,
    load_alarm3_config,
    pause_alarm3_rule,
    save_alarm3_config,
    unpause_alarm3_rule,
)
from dashboard.services.form_utils import parse_int_form_field
from dashboard.services.status_builder import (
    build_status,
    email_alerts_configured,
    get_cached_status,
)

LONDON_TZ = ZoneInfo("Europe/London")


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
pages_routes.register(app)
api_routes.register(app)

# Log Cosmos persistence status at startup so it is visible in Container App log
# streams and makes misconfigured deployments immediately obvious.
if config.COSMOS_ENDPOINT:
    log.info("Cosmos persistence ENABLED — endpoint: %s", config.COSMOS_ENDPOINT)
else:
    log.warning("Cosmos persistence DISABLED — COSMOS_ENDPOINT is not set; alarm config/state will not be persisted")

# ---------------------------------------------------------------------------
# Internationalisation (Flask-Babel)
# ---------------------------------------------------------------------------


def _get_locale() -> str:
    """Return the active locale code from the session, defaulting to the configured language."""
    return session.get("lang", config.DEFAULT_LANGUAGE)


babel = Babel(
    app,
    locale_selector=_get_locale,
    # translations/ lives one level above the Flask root_path (dashboard/dashboard/)
    default_translation_directories=str(Path(__file__).parent.parent / "translations"),
)


@app.context_processor
def inject_language() -> dict:
    """Inject the current language code and environment label into every template context."""
    return {
        "current_lang": session.get("lang", config.DEFAULT_LANGUAGE),
        "environment_label": config.ENVIRONMENT_LABEL,
        "environment_color": config.ENVIRONMENT_COLOR,
    }


# ---------------------------------------------------------------------------
# Simple in-memory cache for /api/status
# ---------------------------------------------------------------------------
# The generic cache engine (TTL storage, stale-while-revalidate, background
# refresh) lives in dashboard.services.cache so it can be unit-tested in
# isolation. Re-imported here under the original names to keep every call
# site in this module (and existing test patches) unchanged.

_cache_lock = cache.cache_lock
_cache_data = cache.cache_data
_cached = cache.cached
_cached_nowait = cache.cached_nowait
_multi_cached_nowait = cache.multi_cached_nowait
_is_cache_stale = cache.is_cache_stale


# ---------------------------------------------------------------------------
# Status/alarm-map builders (system status payload + Flows-page alarm map)
# live in dashboard.services.status_builder so blueprint modules can import
# them without a circular dependency on this module. Re-imported here under
# the original private names to keep every call site (and existing test
# patches of the outer function) unchanged.

_get_cached_status = get_cached_status
_build_status = build_status


# ---------------------------------------------------------------------------
# Page routes (set_language, index, flows_page, exceptions_page,
# service_bus_page, messages_page, trace_page) now live in
# dashboard.routes.pages — registered near the top of this module via
# pages_routes.register(app).
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# API routes (healthz, api_status, api_refresh, api_flows,
# api_container_app_history, api_messages, api_servicebus_metrics,
# api_hl7_throughput, api_alarms_status) now live in dashboard.routes.api —
# registered near the top of this module via api_routes.register(app).
# ---------------------------------------------------------------------------


# This helper still lives in dashboard.services.status_builder alongside
# the other status/alarm-map builders. Re-imported here under the original
# private name so existing call sites (alarm-config pages) keep working.
_email_alerts_configured = email_alerts_configured


# ---------------------------------------------------------------------------
# Alarm page routes
# ---------------------------------------------------------------------------


@app.route("/alarms")
def alarms_overview_page() -> str:
    """Render the Alarms overview page showing all three alarm-type summaries."""
    if request.args.get("refresh") == "1":
        with _cache_lock:
            _cache_data["alarms"]["ts"] = 0.0
            _cache_data["alarm2"]["ts"] = 0.0
            _cache_data["alarm3"]["ts"] = 0.0

    # Fetch all three alarm statuses concurrently — cold fetches run in
    # parallel threads instead of blocking sequentially.
    alarm1_rows, alarm2_rows, alarm3_rows = _multi_cached_nowait(
        [
            ("alarms", get_alarm_status, config.API_CACHE_TTL),
            ("alarm2", get_alarm2_status, config.API_CACHE_TTL),
            ("alarm3", get_alarm3_status, config.API_CACHE_TTL),
        ]
    )

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
        refreshed_at=datetime.now(LONDON_TZ).strftime("%d %b %Y  %H:%M:%S %Z"),
        refresh_interval=int(config.API_CACHE_TTL),
    )


@app.route("/alarms/inactivity")
def alarm_page() -> str:
    """Render the Inactivity Alarm status page (Alarm 1)."""
    alarm_rows = _cached_nowait(
        "alarms",
        get_alarm_status,
        ttl=config.API_CACHE_TTL,
    )
    # Determine whether any alarms have been configured at all
    cfg = load_alarm_config()
    any_configured = any(s.get("alarm_enabled", False) for s in cfg.get("rules", {}).values())
    return render_template(
        "alarm.html",
        alarm_rows=alarm_rows,
        no_alarms_configured=not any_configured,
        config_ok=bool(config.AZURE_LOG_ANALYTICS_WORKSPACE_ID),
        refreshed_at=datetime.now(LONDON_TZ).strftime("%d %b %Y  %H:%M:%S %Z"),
        data_is_stale=_is_cache_stale("alarms"),
    )


@app.route("/alarm-config", methods=["GET", "POST"])
def alarm_config_page() -> str:
    """Render and process the Inactivity Alarm configuration page (Alarm 1).

    GET  – displays the current rule list.
    POST – applies deletions, updates existing rules, and optionally adds a new rule.
    """
    saved = False
    new_rid: str | None = None

    if request.method == "POST":
        cfg = load_alarm_config()
        rules_cfg = cfg.setdefault("rules", {})

        # Handle deletions
        for key in list(request.form):
            if key.startswith("delete_"):
                rid = key[len("delete_") :]
                rules_cfg.setdefault(rid, {})["deleted"] = True

        # Update existing rules
        submitted_ids = [key[len("alerting_gap_") :] for key in request.form if key.startswith("alerting_gap_")]
        for rid in submitted_ids:
            if rules_cfg.get(rid, {}).get("deleted"):
                continue
            entry = rules_cfg.setdefault(rid, {})
            entry["alarm_enabled"] = f"enabled_{rid}" in request.form
            entry["email_alerts_enabled"] = f"email_{rid}" in request.form
            entry["email_ooh_enabled"] = f"email_ooh_{rid}" in request.form and entry["email_alerts_enabled"]
            entry["display_name"] = (request.form.get(f"display_name_{rid}") or "").strip()
            entry["workflow_id"] = (request.form.get(f"workflow_id_{rid}") or "").strip()
            entry["alerting_gap_minutes"] = parse_int_form_field(request.form, f"alerting_gap_{rid}", 60)
            entry["day_threshold_minutes"] = parse_int_form_field(request.form, f"day_threshold_{rid}", 60)
            entry["evening_threshold_minutes"] = parse_int_form_field(request.form, f"evening_threshold_{rid}", 120)
            entry["weekend_threshold_minutes"] = parse_int_form_field(request.form, f"weekend_threshold_{rid}", 240)

        # Add new rule
        new_wid = (request.form.get("new_workflow_id") or "").strip()
        new_rid = None
        if new_wid:
            new_rid = generate_alarm1_rule_id(new_wid, set(rules_cfg))
            rules_cfg[new_rid] = {
                "display_name": (request.form.get("new_display_name") or "").strip(),
                "alarm_enabled": "new_enabled" in request.form,
                "workflow_id": new_wid,
                "day_threshold_minutes": parse_int_form_field(request.form, "new_day_threshold", 60),
                "evening_threshold_minutes": parse_int_form_field(request.form, "new_evening_threshold", 120),
                "weekend_threshold_minutes": parse_int_form_field(request.form, "new_weekend_threshold", 240),
                "alerting_gap_minutes": parse_int_form_field(request.form, "new_alerting_gap", 60),
                "email_alerts_enabled": False,
                "email_ooh_enabled": False,
            }

        save_alarm_config(cfg)
        with _cache_lock:
            _cache_data["alarms"]["ts"] = 0.0
            _cache_data["alarms"]["data"] = None
        saved = True

    rules = get_config_page_data()
    return render_template(
        "alarm_config.html",
        rules=rules,
        saved=saved,
        new_rule_id=new_rid if request.method == "POST" else None,
        config_ok=bool(config.AZURE_LOG_ANALYTICS_WORKSPACE_ID),
        smtp_configured=_email_alerts_configured(),
    )


@app.route("/alarm1/pause/<rule_id>", methods=["POST"])
def alarm1_pause(rule_id: str) -> tuple[Response, int] | Response:
    """Pause an Alarm 1 rule for a given duration with an optional reason.

    Expects a JSON body: ``{"duration_minutes": int, "reason": str}``.
    Optimistically updates the in-memory cache so the page reload is instant
    rather than waiting for a fresh Azure Log Analytics query.
    """
    data = request.get_json(silent=True) or {}
    try:
        duration = int(data.get("duration_minutes", 60))
        if duration < 1:
            raise ValueError("duration_minutes must be >= 1")
    except (TypeError, ValueError) as exc:
        app.logger.warning("Invalid pause request payload: %s", exc)
        return jsonify({"ok": False, "error": "Invalid duration_minutes value."}), 400

    reason = str(data.get("reason", "")).strip()
    pause_alarm_rule(rule_id, duration, reason)

    # Optimistically patch the cached row so the page reload is instant.
    _PAUSE_ORDER = {"paused": 0, "critical": 1, "suppressed": 2, "unknown": 3, "healthy": 4}
    now = datetime.now(LONDON_TZ)
    paused_until_dt = now + timedelta(minutes=duration)
    with _cache_lock:
        cached_rows = _cache_data.get("alarms", {}).get("data")
        if isinstance(cached_rows, list):
            for row in cached_rows:
                if row.get("id") == rule_id:
                    row["status"] = "paused"
                    row["pause_remaining"] = float(duration)
                    row["pause_reason"] = reason
                    row["paused_until"] = paused_until_dt.strftime("%d %b %Y  %H:%M %Z")
                    break
            cached_rows.sort(key=lambda r: _PAUSE_ORDER.get(r.get("status", ""), 9))
            _cache_data["alarms"]["data"] = cached_rows
            _cache_data["alarms"]["ts"] = time.monotonic()  # mark as fresh
    return jsonify({"ok": True})


@app.route("/alarm1/unpause/<rule_id>", methods=["POST"])
def alarm1_unpause(rule_id: str) -> Response:
    """Remove a manual pause from an Alarm 1 rule, restoring normal evaluation.

    Optimistically sets the row to 'unknown' in the cache so the reload is
    instant, then marks the cache as stale so a background refresh re-evaluates
    the true alarm status shortly afterwards.
    """
    unpause_alarm_rule(rule_id)

    # Optimistically patch the cached row: show 'unknown' instantly,
    # then let the stale cache trigger a background re-evaluation.
    _PAUSE_ORDER = {"paused": 0, "critical": 1, "suppressed": 2, "unknown": 3, "healthy": 4}
    with _cache_lock:
        cached_rows = _cache_data.get("alarms", {}).get("data")
        if isinstance(cached_rows, list):
            for row in cached_rows:
                if row.get("id") == rule_id:
                    row["status"] = "unknown"
                    row.pop("pause_remaining", None)
                    row.pop("pause_reason", None)
                    row.pop("paused_until", None)
                    break
            cached_rows.sort(key=lambda r: _PAUSE_ORDER.get(r.get("status", ""), 9))
            _cache_data["alarms"]["data"] = cached_rows
        # Mark stale — background refresh will resolve the true status shortly.
        if "alarms" in _cache_data:
            _cache_data["alarms"]["ts"] = 0.0
    return jsonify({"ok": True})


@app.route("/alarm2/pause/<rule_id>", methods=["POST"])
def alarm2_pause(rule_id: str) -> tuple[Response, int] | Response:
    """Pause an Alarm 2 rule for a given duration with an optional reason."""
    data = request.get_json(silent=True) or {}
    try:
        duration = int(data.get("duration_minutes", 60))
        if duration < 1:
            raise ValueError("duration_minutes must be >= 1")
    except (TypeError, ValueError):
        logging.getLogger(__name__).warning(
            "Invalid pause request payload for alarm2 rule_id=%s",
            rule_id,
            exc_info=True,
        )
        return jsonify({"ok": False, "error": "Invalid duration_minutes value."}), 400

    reason = str(data.get("reason", "")).strip()
    pause_alarm2_rule(rule_id, duration, reason)

    _PAUSE_ORDER = {"paused": 0, "critical": 1, "suppressed": 2, "unknown": 3, "healthy": 4}
    now = datetime.now(LONDON_TZ)
    paused_until_dt = now + timedelta(minutes=duration)
    with _cache_lock:
        cached_rows = _cache_data.get("alarm2", {}).get("data")
        if isinstance(cached_rows, list):
            for row in cached_rows:
                if row.get("id") == rule_id:
                    row["status"] = "paused"
                    row["pause_remaining"] = float(duration)
                    row["pause_reason"] = reason
                    row["paused_until"] = paused_until_dt.strftime("%d %b %Y  %H:%M %Z")
                    break
            cached_rows.sort(key=lambda r: _PAUSE_ORDER.get(r.get("status", ""), 9))
            _cache_data["alarm2"]["data"] = cached_rows
            _cache_data["alarm2"]["ts"] = time.monotonic()
    return jsonify({"ok": True})


@app.route("/alarm2/unpause/<rule_id>", methods=["POST"])
def alarm2_unpause(rule_id: str) -> Response:
    """Remove a manual pause from an Alarm 2 rule, restoring normal evaluation."""
    unpause_alarm2_rule(rule_id)

    _PAUSE_ORDER = {"paused": 0, "critical": 1, "suppressed": 2, "unknown": 3, "healthy": 4}
    with _cache_lock:
        cached_rows = _cache_data.get("alarm2", {}).get("data")
        if isinstance(cached_rows, list):
            for row in cached_rows:
                if row.get("id") == rule_id:
                    row["status"] = "unknown"
                    row.pop("pause_remaining", None)
                    row.pop("pause_reason", None)
                    row.pop("paused_until", None)
                    break
            cached_rows.sort(key=lambda r: _PAUSE_ORDER.get(r.get("status", ""), 9))
            _cache_data["alarm2"]["data"] = cached_rows
        if "alarm2" in _cache_data:
            _cache_data["alarm2"]["ts"] = 0.0
    return jsonify({"ok": True})


@app.route("/alarm3/pause/<rule_id>", methods=["POST"])
def alarm3_pause(rule_id: str) -> tuple[Response, int] | Response:
    """Pause an Alarm 3 rule for a given duration with an optional reason."""
    data = request.get_json(silent=True) or {}
    try:
        duration = int(data.get("duration_minutes", 60))
        if duration < 1:
            raise ValueError("duration_minutes must be >= 1")
    except (TypeError, ValueError):
        logging.warning("Invalid alarm3 pause payload", exc_info=True)
        return jsonify({"ok": False, "error": "Invalid request payload."}), 400

    reason = str(data.get("reason", "")).strip()
    pause_alarm3_rule(rule_id, duration, reason)

    _PAUSE_ORDER = {"paused": 0, "critical": 1, "suppressed": 2, "unknown": 3, "healthy": 4}
    now = datetime.now(LONDON_TZ)
    paused_until_dt = now + timedelta(minutes=duration)
    with _cache_lock:
        cached_rows = _cache_data.get("alarm3", {}).get("data")
        if isinstance(cached_rows, list):
            for row in cached_rows:
                if row.get("id") == rule_id:
                    row["status"] = "paused"
                    row["pause_remaining"] = float(duration)
                    row["pause_reason"] = reason
                    row["paused_until"] = paused_until_dt.strftime("%d %b %Y  %H:%M %Z")
                    break
            cached_rows.sort(key=lambda r: _PAUSE_ORDER.get(r.get("status", ""), 9))
            _cache_data["alarm3"]["data"] = cached_rows
            _cache_data["alarm3"]["ts"] = time.monotonic()
    return jsonify({"ok": True})


@app.route("/alarm3/unpause/<rule_id>", methods=["POST"])
def alarm3_unpause(rule_id: str) -> Response:
    """Remove a manual pause from an Alarm 3 rule, restoring normal evaluation."""
    unpause_alarm3_rule(rule_id)

    _PAUSE_ORDER = {"paused": 0, "critical": 1, "suppressed": 2, "unknown": 3, "healthy": 4}
    with _cache_lock:
        cached_rows = _cache_data.get("alarm3", {}).get("data")
        if isinstance(cached_rows, list):
            for row in cached_rows:
                if row.get("id") == rule_id:
                    row["status"] = "unknown"
                    row.pop("pause_remaining", None)
                    row.pop("pause_reason", None)
                    row.pop("paused_until", None)
                    break
            cached_rows.sort(key=lambda r: _PAUSE_ORDER.get(r.get("status", ""), 9))
            _cache_data["alarm3"]["data"] = cached_rows
        if "alarm3" in _cache_data:
            _cache_data["alarm3"]["ts"] = 0.0
    return jsonify({"ok": True})


@app.route("/alarms/outgoing-messages")
def alarm2_page() -> str:
    """Render the Outgoing Messages Alarm status page (Alarm 2)."""
    alarm2_rows = _cached_nowait(
        "alarm2",
        get_alarm2_status,
        ttl=config.API_CACHE_TTL,
    )
    cfg = load_alarm2_config()
    any_configured = any(r.get("alarm_enabled", False) for r in cfg.get("rules", {}).values())
    return render_template(
        "alarm2.html",
        alarm2_rows=alarm2_rows,
        no_alarms_configured=not any_configured,
        config_ok=bool(config.AZURE_LOG_ANALYTICS_WORKSPACE_ID),
        refreshed_at=datetime.now(LONDON_TZ).strftime("%d %b %Y  %H:%M:%S %Z"),
        data_is_stale=_is_cache_stale("alarm2"),
    )


@app.route("/alarm2-config", methods=["GET", "POST"])
def alarm2_config_page() -> str:
    """Render and process the Outgoing Messages Alarm configuration page (Alarm 2).

    GET  – displays the current rule list.
    POST – applies deletions, updates existing rules, and optionally adds a new rule.
    """
    saved = False
    new_id: str | None = None

    if request.method == "POST":
        cfg = load_alarm2_config()
        rules_cfg = cfg.setdefault("rules", {})

        # --- Handle deletions first ---
        for key in list(request.form):
            if key.startswith("delete_"):
                rid = key[len("delete_") :]
                rules_cfg.setdefault(rid, {})["deleted"] = True

        # --- Update existing rules (skip deleted) ---
        submitted_ids = [key[len("alerting_gap_") :] for key in request.form if key.startswith("alerting_gap_")]
        for rid in submitted_ids:
            if rules_cfg.get(rid, {}).get("deleted"):
                continue
            entry = rules_cfg.setdefault(rid, {})
            entry["alarm_enabled"] = f"enabled_{rid}" in request.form
            entry["email_alerts_enabled"] = f"email_{rid}" in request.form
            entry["email_ooh_enabled"] = f"email_ooh_{rid}" in request.form and entry["email_alerts_enabled"]
            entry["display_name"] = (request.form.get(f"display_name_{rid}") or "").strip()
            entry["workflow_id"] = (request.form.get(f"workflow_id_{rid}") or "").strip()
            entry["day_threshold_minutes"] = parse_int_form_field(request.form, f"day_threshold_{rid}", 60, minimum=0)
            entry["evening_threshold_minutes"] = parse_int_form_field(
                request.form, f"evening_threshold_{rid}", 120, minimum=0
            )
            entry["weekend_threshold_minutes"] = parse_int_form_field(
                request.form, f"weekend_threshold_{rid}", 240, minimum=0
            )
            entry["alerting_gap_minutes"] = parse_int_form_field(request.form, f"alerting_gap_{rid}", 60, minimum=1)

        # --- Add new rule if submitted ---
        new_wid = (request.form.get("new_workflow_id") or "").strip()
        new_id = None
        if new_wid:
            new_id = generate_rule_id(new_wid, set(rules_cfg))
            rules_cfg[new_id] = {
                "display_name": (request.form.get("new_display_name") or "").strip() or new_wid,
                "alarm_enabled": "new_enabled" in request.form,
                "workflow_id": new_wid,
                "day_threshold_minutes": parse_int_form_field(request.form, "new_day_threshold", 60, minimum=0),
                "evening_threshold_minutes": parse_int_form_field(
                    request.form, "new_evening_threshold", 120, minimum=0
                ),
                "weekend_threshold_minutes": parse_int_form_field(
                    request.form, "new_weekend_threshold", 240, minimum=0
                ),
                "alerting_gap_minutes": parse_int_form_field(request.form, "new_alerting_gap", 60, minimum=1),
                "email_alerts_enabled": False,
                "email_ooh_enabled": False,
            }

        save_alarm2_config(cfg)
        with _cache_lock:
            _cache_data["alarm2"]["ts"] = 0.0
            _cache_data["alarm2"]["data"] = None
        saved = True

    rules = get_alarm2_config_page_data()
    return render_template(
        "alarm2_config.html",
        rules=rules,
        saved=saved,
        new_rule_id=new_id if request.method == "POST" else None,
        config_ok=bool(config.AZURE_LOG_ANALYTICS_WORKSPACE_ID),
        smtp_configured=_email_alerts_configured(),
    )


@app.route("/alarms/failures")
def alarm3_page() -> str:
    """Render the Failures Alarm status page (Alarm 3)."""
    alarm3_rows = _cached_nowait(
        "alarm3",
        get_alarm3_status,
        ttl=config.API_CACHE_TTL,
    )
    cfg = load_alarm3_config()
    any_configured = any(r.get("alarm_enabled", False) for r in cfg.get("rules", {}).values())
    return render_template(
        "alarm3.html",
        alarm3_rows=alarm3_rows,
        no_alarms_configured=not any_configured,
        config_ok=bool(config.AZURE_LOG_ANALYTICS_WORKSPACE_ID),
        refreshed_at=datetime.now(LONDON_TZ).strftime("%d %b %Y  %H:%M:%S %Z"),
        data_is_stale=_is_cache_stale("alarm3"),
    )


@app.route("/alarm3-config", methods=["GET", "POST"])
def alarm3_config_page() -> str:
    """Render and process the Failures Alarm configuration page (Alarm 3).

    GET  – displays the current rule list.
    POST – applies deletions, updates existing rules, and optionally adds a new rule.
    """
    saved = False
    new_id: str | None = None

    if request.method == "POST":
        cfg = load_alarm3_config()
        rules_cfg = cfg.setdefault("rules", {})

        for key in list(request.form):
            if key.startswith("delete_"):
                rid = key[len("delete_") :]
                rules_cfg.setdefault(rid, {})["deleted"] = True

        submitted_ids = [key[len("alerting_gap_") :] for key in request.form if key.startswith("alerting_gap_")]
        for rid in submitted_ids:
            if rules_cfg.get(rid, {}).get("deleted"):
                continue
            entry = rules_cfg.setdefault(rid, {})
            entry["alarm_enabled"] = f"enabled_{rid}" in request.form
            entry["email_alerts_enabled"] = f"email_{rid}" in request.form
            entry["email_ooh_enabled"] = f"email_ooh_{rid}" in request.form and entry["email_alerts_enabled"]
            entry["display_name"] = (request.form.get(f"display_name_{rid}") or "").strip()
            entry["workflow_id"] = (request.form.get(f"workflow_id_{rid}") or "").strip()
            entry["window_duration_minutes"] = parse_int_form_field(
                request.form, f"window_duration_{rid}", 15, minimum=1
            )
            entry["threshold"] = parse_int_form_field(request.form, f"threshold_{rid}", 1, minimum=1)
            entry["alerting_gap_minutes"] = parse_int_form_field(request.form, f"alerting_gap_{rid}", 60, minimum=1)

        new_wid = (request.form.get("new_workflow_id") or "").strip()
        new_id = None
        if new_wid:
            new_id = generate_alarm3_rule_id(new_wid, set(rules_cfg))
            rules_cfg[new_id] = {
                "display_name": (request.form.get("new_display_name") or "").strip() or f"{new_wid} Failures",
                "alarm_enabled": "new_enabled" in request.form,
                "workflow_id": new_wid,
                "window_duration_minutes": parse_int_form_field(request.form, "new_window_duration", 15, minimum=1),
                "threshold": parse_int_form_field(request.form, "new_threshold", 1, minimum=1),
                "alerting_gap_minutes": parse_int_form_field(request.form, "new_alerting_gap", 60, minimum=1),
                "email_alerts_enabled": False,
                "email_ooh_enabled": False,
            }

        save_alarm3_config(cfg)
        with _cache_lock:
            _cache_data["alarm3"]["ts"] = 0.0
            _cache_data["alarm3"]["data"] = None
        saved = True

    rules = get_alarm3_config_page_data()
    return render_template(
        "alarm3_config.html",
        rules=rules,
        saved=saved,
        new_rule_id=new_id if request.method == "POST" else None,
        config_ok=bool(config.AZURE_LOG_ANALYTICS_WORKSPACE_ID),
        smtp_configured=_email_alerts_configured(),
    )


@app.template_filter("format_bytes")
def format_bytes(size: int | float) -> str:
    """Jinja2 filter: convert a byte count to a human-readable string (e.g. ``1.4 MB``)."""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size = size / 1024
    return f"{size:.1f} TB"


@app.template_filter("health_badge")
def health_badge(health: str) -> str:
    """Jinja2 filter: map a health string to a Bootstrap colour token (e.g. ``"healthy"`` → ``"success"``)."""
    colours = {
        "healthy": "success",
        "warning": "warning",
        "critical": "danger",
        "unknown": "secondary",
    }
    return colours.get(health, "secondary")


if __name__ == "__main__":
    app.run(debug=config.FLASK_DEBUG, host="127.0.0.1", port=8080)
