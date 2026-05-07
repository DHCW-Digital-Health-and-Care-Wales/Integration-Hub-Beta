import signal
import unittest
from types import FrameType
from typing import Optional
from unittest.mock import MagicMock, patch

from processor_manager_lib import ProcessorManager


class TestProcessorManager(unittest.TestCase):

    def setUp(self) -> None:
        self.processor_manager = ProcessorManager()

    def test_initialization_sets_running_to_true(self) -> None:
        # Assert
        self.assertTrue(self.processor_manager.is_running)

    @patch('processor_manager_lib.processor_manager.signal.signal')
    def test_setup_signal_handlers_registers_signals(self, mock_signal: MagicMock) -> None:
        # Arrange & Act
        processor_manager = ProcessorManager()

        # Assert
        mock_signal.assert_any_call(signal.SIGINT, processor_manager._shutdown_handler)
        mock_signal.assert_any_call(signal.SIGTERM, processor_manager._shutdown_handler)
        self.assertEqual(mock_signal.call_count, 2)

    @patch('processor_manager_lib.processor_manager.logger')
    def test_shutdown_handler_stops_processor_and_logs(self, mock_logger: MagicMock) -> None:
        # Arrange
        signum = signal.SIGINT
        frame: Optional[FrameType] = None

        # Act
        self.processor_manager._shutdown_handler(signum, frame)

        # Assert
        self.assertFalse(self.processor_manager.is_running)
        mock_logger.info.assert_called_once_with("Shutting down the processor")

    @patch('processor_manager_lib.processor_manager.logger')
    def test_shutdown_handler_with_sigterm(self, mock_logger: MagicMock) -> None:
        # Arrange
        signum = signal.SIGTERM
        frame: Optional[FrameType] = None

        # Act
        self.processor_manager._shutdown_handler(signum, frame)

        # Assert
        self.assertFalse(self.processor_manager.is_running)
        mock_logger.info.assert_called_once_with("Shutting down the processor")

    @patch('processor_manager_lib.processor_manager.logger')
    def test_stop_method_sets_running_false_and_logs(self, mock_logger: MagicMock) -> None:
        # Arrange
        self.assertTrue(self.processor_manager.is_running)

        # Act
        self.processor_manager.stop()

        # Assert
        self.assertFalse(self.processor_manager.is_running)
        mock_logger.info.assert_called_once_with("Manual processor stop requested")


class TestWrapHandler(unittest.TestCase):

    def setUp(self) -> None:
        self.pm = ProcessorManager()

    def test_wrap_handler_returns_original_when_otel_lib_missing(self) -> None:
        handler = MagicMock(return_value=True)
        with patch.dict("sys.modules", {"otel_lib": None}):
            wrapped = self.pm.wrap_handler(handler, "test-service", "test-queue")
        # Should return the original handler unchanged (ImportError path)
        wrapped_result = wrapped("msg")
        handler.assert_called_once_with("msg")
        self.assertTrue(wrapped_result)

    def test_wrap_handler_returns_original_when_provider_is_proxy(self) -> None:
        import opentelemetry.trace as otel_trace
        handler = MagicMock(return_value=True)

        proxy_provider = otel_trace.ProxyTracerProvider()
        with patch("opentelemetry.trace.get_tracer_provider", return_value=proxy_provider):
            wrapped = self.pm.wrap_handler(handler, "test-service", "test-queue")

        self.assertIs(wrapped, handler)

    def test_wrap_handler_wraps_with_real_provider(self) -> None:
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
        from otel_lib import get_tracer

        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))

        handler = MagicMock(return_value=True)

        with patch("opentelemetry.trace.get_tracer_provider", return_value=provider):
            with patch("otel_lib.get_tracer", wraps=get_tracer):
                wrapped = self.pm.wrap_handler(handler, "my-service", "my-queue")

        msg = MagicMock()
        msg.message_id = "test-id-123"
        result = wrapped(msg)
        self.assertTrue(result)
        handler.assert_called_once_with(msg)

    def test_wrap_handler_records_exception_and_reraises(self) -> None:
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
        from opentelemetry.trace import StatusCode
        from otel_lib import get_tracer

        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))

        def failing_handler(msg: object) -> bool:
            raise ValueError("processing error")

        with patch("opentelemetry.trace.get_tracer_provider", return_value=provider):
            with patch("otel_lib.get_tracer", wraps=get_tracer):
                wrapped = self.pm.wrap_handler(failing_handler, "my-service", "my-queue")

        with self.assertRaises(ValueError):
            wrapped(MagicMock())

        spans = exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].status.status_code, StatusCode.ERROR)

    def test_wrap_handler_span_name_includes_service_name(self) -> None:
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
        from otel_lib import get_tracer

        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))

        handler = MagicMock(return_value=True)

        with patch("opentelemetry.trace.get_tracer_provider", return_value=provider):
            with patch("otel_lib.get_tracer", wraps=get_tracer):
                wrapped = self.pm.wrap_handler(handler, "phw-transformer", "ingress-queue")

        wrapped(MagicMock())
        spans = exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].name, "phw-transformer.process_message")

    def test_wrap_handler_sets_messaging_attributes(self) -> None:
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
        from otel_lib import get_tracer

        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))

        handler = MagicMock(return_value=True)
        msg = MagicMock()
        msg.message_id = "abc-123"

        with patch("opentelemetry.trace.get_tracer_provider", return_value=provider):
            with patch("otel_lib.get_tracer", wraps=get_tracer):
                wrapped = self.pm.wrap_handler(handler, "svc", "my-queue")

        wrapped(msg)
        spans = exporter.get_finished_spans()
        attrs = spans[0].attributes
        self.assertEqual(attrs.get("messaging.system"), "azure_service_bus")
        self.assertEqual(attrs.get("messaging.destination"), "my-queue")
        self.assertEqual(attrs.get("messaging.message_id"), "abc-123")


if __name__ == '__main__':
    unittest.main()
