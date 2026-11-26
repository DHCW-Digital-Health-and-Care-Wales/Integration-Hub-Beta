import logging
import signal
import threading
from types import FrameType
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class ProcessorManager:

    def __init__(self) -> None:
        self._running = True
        self._shutdown_event = threading.Event()
        self._callbacks_done = threading.Event()
        self._callbacks_lock = threading.Lock()
        self._callbacks_invoked = False
        self._shutdown_callbacks: list[Callable[[], None]] = []
        self._coordinator_thread: Optional[threading.Thread] = None
        self._setup_signal_handlers()

    def _setup_signal_handlers(self) -> None:
        signal.signal(signal.SIGINT, self._shutdown_handler)
        signal.signal(signal.SIGTERM, self._shutdown_handler)

    def _ensure_coordinator_started(self) -> None:
        if self._coordinator_thread is not None:
            return
        thread = threading.Thread(
            target=self._run_shutdown_coordinator,
            name="processor-shutdown-coordinator",
            daemon=True,
        )
        self._coordinator_thread = thread
        thread.start()

    def _run_shutdown_coordinator(self) -> None:
        self._shutdown_event.wait()
        self._invoke_shutdown_callbacks()

    def _invoke_shutdown_callbacks(self) -> None:
        with self._callbacks_lock:
            if self._callbacks_invoked:
                return
            self._callbacks_invoked = True
            callbacks = list(self._shutdown_callbacks)

        try:
            for callback in callbacks:
                try:
                    callback()
                except Exception as exc:
                    logger.warning("Shutdown callback failed: %s", exc)
        finally:
            self._callbacks_done.set()

    def _shutdown_handler(self, signum: int, frame: Optional[FrameType]) -> None:
        logger.info("Shutting down the processor")
        self._running = False
        # Only set the shutdown event inside the signal handler; registered callbacks
        # run on the shutdown coordinator thread so lock-taking callbacks (such as
        # TCPHealthCheckServer.stop()) can never deadlock on signal re-entry.
        self._shutdown_event.set()

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def shutdown_event(self) -> threading.Event:
        return self._shutdown_event

    def register_shutdown_callback(self, callback: Callable[[], None]) -> None:
        """Register a callback invoked promptly off-signal-handler when shutdown is triggered."""
        already_invoked = False
        with self._callbacks_lock:
            if self._callbacks_invoked:
                already_invoked = True
            else:
                self._shutdown_callbacks.append(callback)
                self._ensure_coordinator_started()
        if already_invoked:
            try:
                callback()
            except Exception as exc:
                logger.warning("Shutdown callback failed: %s", exc)

    def stop(self) -> None:
        logger.info("Manual processor stop requested")
        self._running = False
        self._shutdown_event.set()
        self._invoke_shutdown_callbacks()

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
            import opentelemetry.trace as otel_trace  # noqa: PLC0415
            from opentelemetry.trace import StatusCode  # noqa: PLC0415
            from otel_lib import get_tracer  # noqa: PLC0415

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
