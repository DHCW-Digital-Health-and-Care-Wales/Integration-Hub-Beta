"""
Integration Hub Dashboard — Flask application entry point.
"""

from __future__ import annotations

import logging
import os
import ssl
import tempfile
from pathlib import Path

from flask import Flask, session
from flask_babel import Babel  # type: ignore[import-untyped]

import dashboard.config as config
from dashboard.routes import alarm_config as alarm_config_routes
from dashboard.routes import alarms as alarms_routes
from dashboard.routes import api as api_routes
from dashboard.routes import pages as pages_routes
from dashboard.services.status_builder import (
    build_status,
    email_alerts_configured,
    get_cached_status,
)


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
alarms_routes.register(app)
alarm_config_routes.register(app)

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
# The generic cache engine (TTL storage, stale-while-revalidate, background
# refresh) lives in dashboard.services.cache. All route modules that need it
# (dashboard.routes.pages/api/alarms/alarm_config) import it directly; no
# aliases are re-exported here any more since every cache-touching route has
# now moved out of this module.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Status/alarm-map builders (system status payload + Flows-page alarm map)
# live in dashboard.services.status_builder so blueprint modules can import
# them without a circular dependency on this module. Re-imported here under
# the original private names to keep existing test patches
# (dashboard.app._get_cached_status, dashboard.app._email_alerts_configured)
# working.
# ---------------------------------------------------------------------------

_get_cached_status = get_cached_status
_build_status = build_status
_email_alerts_configured = email_alerts_configured


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


# ---------------------------------------------------------------------------
# Alarm page routes (alarms_overview_page, alarm_page, alarm2_page,
# alarm3_page, alarm1/2/3 pause+unpause) now live in dashboard.routes.alarms
# — registered near the top of this module via alarms_routes.register(app).
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Alarm config routes (alarm_config_page, alarm2_config_page,
# alarm3_config_page) now live in dashboard.routes.alarm_config —
# registered near the top of this module via alarm_config_routes.register(app).
# ---------------------------------------------------------------------------


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
