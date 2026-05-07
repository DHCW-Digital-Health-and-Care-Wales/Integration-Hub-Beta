import logging
import os
from typing import Any

import opentelemetry.context as otel_context
import opentelemetry.trace as otel_trace
from opentelemetry import trace
from opentelemetry.propagate import extract, inject
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

try:
    from azure.monitor.opentelemetry import configure_azure_monitor  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    configure_azure_monitor = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

_otel_configured: bool = False


def configure_otel(service_name: str, service_version: str = "1.0.0") -> bool:
    """Configure OpenTelemetry for the service.

    Reads APPLICATIONINSIGHTS_CONNECTION_STRING from the environment. If the
    variable is absent or empty, a no-op provider is used so the service starts
    cleanly without telemetry.

    Also installs an OtelCorrelationFilter on the root logger so every log
    record carries the current trace_id and span_id.

    Args:
        service_name: The OTel service.name resource attribute (e.g. "phw-hl7-transformer").
        service_version: The OTel service.version resource attribute.

    Returns:
        True to indicate OTel has been configured.
    """
    connection_string = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "").strip()

    if connection_string:
        _configure_azure_monitor(service_name, service_version)
    else:
        logger.info(
            "APPLICATIONINSIGHTS_CONNECTION_STRING not set — OpenTelemetry running with no-op exporter."
        )
        _configure_noop(service_name, service_version)

    _install_log_filter()
    return True


def _configure_azure_monitor(service_name: str, service_version: str) -> None:
    """Configure OTel to export to Azure Monitor / Application Insights."""
    try:
        # azure-monitor-opentelemetry sets up the TracerProvider internally; we
        # only need to supply the resource so the service.name is correct.
        # Disable instrumentors for libraries not used by our HL7 services to
        # prevent ModuleNotFoundError when e.g. psycopg2 is not installed.
        configure_azure_monitor(
            resource=Resource.create(
                {
                    "service.name": service_name,
                    "service.version": service_version,
                }
            ),
            instrumentation_options={
                "django":   {"enabled": False},
                "fastapi":  {"enabled": False},
                "flask":    {"enabled": False},
                "psycopg2": {"enabled": False},
            },
        ) # type: ignore
        logger.info("OpenTelemetry configured with Azure Monitor exporter for service '%s'.", service_name)
    except Exception:
        logger.exception("Failed to configure Azure Monitor exporter — falling back to no-op.")
        _configure_noop(service_name, service_version)


def _configure_noop(service_name: str, service_version: str) -> None:
    """Install a minimal TracerProvider with an in-memory (effectively no-op) exporter."""
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": service_version,
        }
    )
    provider = TracerProvider(resource=resource)
    # InMemorySpanExporter discards spans; this keeps OTel APIs functional without output.
    provider.add_span_processor(SimpleSpanProcessor(InMemorySpanExporter()))
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
