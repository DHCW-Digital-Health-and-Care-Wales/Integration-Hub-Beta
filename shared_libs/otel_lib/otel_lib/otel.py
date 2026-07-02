import logging
import os
from typing import Any

import opentelemetry.context as otel_context
import opentelemetry.trace as otel_trace
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
from opentelemetry import trace
from opentelemetry.propagate import extract, inject
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider

try:
    from azure.monitor.opentelemetry import configure_azure_monitor  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    configure_azure_monitor = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)

_otel_configured: bool = False


def is_configured() -> bool:
    """Return True if ``configure_otel`` has already been called successfully."""
    return _otel_configured


def configure_otel(service_name: str, service_version: str = "1.0.0") -> bool:
    """Configure OpenTelemetry for the service.

    Reads APPLICATIONINSIGHTS_CONNECTION_STRING from the environment. If the
    variable is absent or empty, a no-op provider is used so the service starts
    cleanly without telemetry.

    Also installs an OtelCorrelationFilter on the root logger so every log
    record carries the current trace_id and span_id.

    This function is safe to call multiple times — subsequent calls are no-ops.

    Args:
        service_name: The OTel service.name resource attribute (e.g. "phw-hl7-transformer").
        service_version: The OTel service.version resource attribute.

    Returns:
        True to indicate OTel has been configured.
    """
    global _otel_configured  # noqa: PLW0603
    if _otel_configured:
        logger.debug("OpenTelemetry already configured — skipping re-initialisation.")
        return True

    # Set service name via standard OTel environment variable (used by Azure SDK).
    # Use setdefault only if the variable is absent or blank — an empty/whitespace
    # value can occur in container env configs and must be replaced with the real name.
    if not os.environ.get("OTEL_SERVICE_NAME", "").strip():
        os.environ["OTEL_SERVICE_NAME"] = service_name

    connection_string = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "").strip()

    if connection_string:
        _configure_azure_monitor(service_name, service_version)
    else:
        logger.info(
            "APPLICATIONINSIGHTS_CONNECTION_STRING not set — OpenTelemetry running with no-op exporter."
        )
        _configure_noop(service_name, service_version)

    _install_log_filter()
    _otel_configured = True
    return True


def _configure_azure_monitor(service_name: str, service_version: str) -> None:
    """Configure OTel to export to Azure Monitor / Application Insights."""
    try:
        credential = _get_credential()

        # azure-monitor-opentelemetry configures the TracerProvider and MeterProvider
        # internally; we provide credential and resource for explicit service metadata.
        #
        # Disable ALL auto-instrumentors — our HL7 services use manual
        # telemetry only (EventLogger, wrap_handler spans).  Active
        # auto-instrumentors create spans and HTTP-client metrics for every
        # Azure SDK / urllib3 call, and azure_sdk tracing wraps every Service
        # Bus send/receive.  The resulting metric time-series accumulate
        # without bound inside the MeterProvider and cause steadily growing
        # CPU usage over the lifetime of the container.
        #
        # Pre-set OTEL_PYTHON_DISABLED_INSTRUMENTATIONS so the OTel distro
        # bootstrapper skips the dependency-existence probe for libraries we
        # don't use (e.g. psycopg2).  The instrumentation_options below do the
        # same thing, but only AFTER the initial probe that emits
        # "No module named 'psycopg2'" noise in the logs.
        if not os.environ.get("OTEL_PYTHON_DISABLED_INSTRUMENTATIONS"):
            os.environ["OTEL_PYTHON_DISABLED_INSTRUMENTATIONS"] = (
                "azure_sdk,django,fastapi,flask,psycopg2,requests,urllib,urllib3"
            )
        configure_azure_monitor(
            credential=credential,
            resource=Resource.create(
                {
                    "service.name": service_name,
                    "service.version": service_version,
                }
            ),
            instrumentation_options={
                "azure_sdk": {"enabled": False},
                "django":    {"enabled": False},
                "fastapi":   {"enabled": False},
                "flask":     {"enabled": False},
                "psycopg2":  {"enabled": False},
                "requests":  {"enabled": False},
                "urllib":    {"enabled": False},
                "urllib3":   {"enabled": False},
            },
        ) # type: ignore
        logger.info("OpenTelemetry configured with Azure Monitor exporter for service '%s'.", service_name)
    except Exception:
        logger.exception("Failed to configure Azure Monitor exporter — falling back to no-op.")
        _configure_noop(service_name, service_version)


def _get_credential() -> ManagedIdentityCredential | DefaultAzureCredential:
    """Return an Azure credential for Application Insights ingestion.

    Uses user-assigned managed identity when INSIGHTS_UAMI_CLIENT_ID is set,
    otherwise falls back to DefaultAzureCredential.
    """
    uami_client_id = os.getenv("INSIGHTS_UAMI_CLIENT_ID", "").strip()
    if uami_client_id:
        logger.debug("Using ManagedIdentityCredential (INSIGHTS_UAMI_CLIENT_ID set)")
        return ManagedIdentityCredential(client_id=uami_client_id)

    logger.debug("Using DefaultAzureCredential (INSIGHTS_UAMI_CLIENT_ID not set)")
    return DefaultAzureCredential()


def _configure_noop(service_name: str, service_version: str) -> None:
    """Install a minimal TracerProvider with no exporter.

    Without a SpanProcessor, finished spans are silently discarded and
    garbage-collected.  Previous versions used ``InMemorySpanExporter``
    which stored every span in an ever-growing list, causing a memory leak
    in long-running services.
    """
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": service_version,
        }
    )
    provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(provider)


def _install_log_filter() -> None:
    """Add OtelCorrelationFilter to the root logger if not already present."""
    root_logger = logging.getLogger()
    for existing_filter in root_logger.filters:
        if isinstance(existing_filter, OtelCorrelationFilter):
            return
    root_logger.addFilter(OtelCorrelationFilter())


def get_tracer(name: str) -> otel_trace.Tracer:
    """Return a tracer for the given instrumentation scope name.

    Args:
        name: Typically ``__name__`` of the calling module.

    Returns:
        An OpenTelemetry Tracer instance.
    """
    return trace.get_tracer(name)


def inject_trace_context(properties: dict[str, Any]) -> dict[str, Any]:
    """Inject W3C traceparent/tracestate into a properties dict.

    Intended for use with Azure Service Bus ``application_properties`` on outgoing messages.

    Args:
        properties: Existing message properties dict (will not be mutated; a copy is returned).

    Returns:
        A new dict containing the original properties plus any OTel propagation headers.
    """
    carrier: dict[str, Any] = dict(properties)
    inject(carrier)
    return carrier


def extract_trace_context(properties: dict[str, Any]) -> otel_context.Context:
    """Extract W3C trace context from a properties dict.

    Intended for use with Azure Service Bus ``application_properties`` on incoming messages.

    Args:
        properties: Message application_properties from a received Service Bus message.

    Returns:
        An OpenTelemetry Context containing the remote trace context (or an empty context
        if no propagation headers are present).
    """
    return extract(properties or {})


class OtelCorrelationFilter(logging.Filter):
    """Logging filter that attaches the active OTel trace_id and span_id to every record.

    Fields added:
        otel_trace_id (str): 32-hex-character trace ID, or "0" * 32 when no active span.
        otel_span_id (str): 16-hex-character span ID, or "0" * 16 when no active span.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        span = otel_trace.get_current_span()
        ctx = span.get_span_context()
        if ctx and ctx.is_valid:
            record.otel_trace_id = format(ctx.trace_id, "032x")
            record.otel_span_id = format(ctx.span_id, "016x")
        else:
            record.otel_trace_id = "0" * 32
            record.otel_span_id = "0" * 16
        return True
