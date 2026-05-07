import logging
import signal
from typing import Any, Callable, Optional
from types import FrameType

logger = logging.getLogger(__name__)


class ProcessorManager:

    def __init__(self) -> None:
        self._running = True
        self._setup_signal_handlers()

    def _setup_signal_handlers(self) -> None:
        signal.signal(signal.SIGINT, self._shutdown_handler)
        signal.signal(signal.SIGTERM, self._shutdown_handler)

    def _shutdown_handler(self, signum: int, frame: Optional[FrameType]) -> None:
        logger.info("Shutting down the processor")
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def stop(self) -> None:
        logger.info("Manual processor stop requested")
        self._running = False

    def wrap_handler(
        self,
        handler: Callable[[Any], bool],
        service_name: str,
        queue_name: str,
    ) -> Callable[[Any], bool]:
        """Return a version of *handler* wrapped in an OTel span.

        If ``otel_lib`` is not installed or OTel has not been configured, the
        original handler is returned unchanged so there is zero overhead.

        Args:
            handler: The user-supplied message processing callable.
            service_name: Used to build the span name (``"{service_name}.process_message"``).
            queue_name: Set as the ``messaging.destination`` span attribute.

        Returns:
            A callable with the same signature as *handler*.
        """
        try:
            import opentelemetry.trace as otel_trace
            from opentelemetry.trace import StatusCode
            from otel_lib import get_tracer

            # Only instrument when a real TracerProvider has been installed.
            provider = otel_trace.get_tracer_provider()
            if isinstance(provider, otel_trace.ProxyTracerProvider):
                logger.debug("OTel not configured — skipping span wrapping for handler.")
                return handler

            tracer = get_tracer(__name__)
            span_name = f"{service_name}.process_message"

            def _wrapped(message: Any) -> bool:
                with tracer.start_as_current_span(span_name) as span:
                    span.set_attribute("messaging.system", "azure_service_bus")
                    span.set_attribute("messaging.destination", queue_name)
                    msg_id = getattr(message, "message_id", None)
                    if msg_id:
                        span.set_attribute("messaging.message_id", str(msg_id))
                    try:
                        return handler(message)
                    except Exception as exc:
                        span.record_exception(exc)
                        span.set_status(StatusCode.ERROR, str(exc))
                        raise

            return _wrapped
        except ImportError:
            logger.debug("otel_lib not available — skipping span wrapping for handler.")
            return handler
