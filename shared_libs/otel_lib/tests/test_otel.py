import logging
import unittest
from unittest.mock import patch

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

import otel_lib.otel as otel_module
from otel_lib import (
    OtelCorrelationFilter,
    configure_otel,
    extract_trace_context,
    get_tracer,
    inject_trace_context,
    is_configured,
)
from otel_lib.otel import _configure_noop


class TestConfigureOtel(unittest.TestCase):

    def setUp(self) -> None:
        otel_module._otel_configured = False
        # Reset root logger filters between tests
        root_logger = logging.getLogger()
        root_logger.filters = []

    def tearDown(self) -> None:
        otel_module._otel_configured = False
        root_logger = logging.getLogger()
        root_logger.filters = []

    @patch.dict("os.environ", {}, clear=True)
    def test_configure_otel_no_connection_string_uses_noop(self) -> None:
        configure_otel("test-service")
        provider = trace.get_tracer_provider()
        self.assertIsInstance(provider, TracerProvider)

    @patch.dict("os.environ", {"APPLICATIONINSIGHTS_CONNECTION_STRING": ""}, clear=True)
    def test_configure_otel_empty_connection_string_uses_noop(self) -> None:
        configure_otel("test-service")
        provider = trace.get_tracer_provider()
        self.assertIsInstance(provider, TracerProvider)

    @patch.dict(
        "os.environ",
        {"APPLICATIONINSIGHTS_CONNECTION_STRING": "InstrumentationKey=fake-key;IngestionEndpoint=https://example.com"},
        clear=True,
    )
    def test_configure_otel_with_connection_string_calls_azure_monitor(self) -> None:
        with patch("otel_lib.otel.configure_azure_monitor") as mock_configure, \
             patch("otel_lib.otel.DefaultAzureCredential") as mock_default_credential:
            configure_otel("test-service")
            mock_configure.assert_called_once()
            _, kwargs = mock_configure.call_args
            self.assertIn("credential", kwargs)
            self.assertEqual(kwargs["credential"], mock_default_credential.return_value)
            opts = kwargs["instrumentation_options"]
            # Every supported auto-instrumentor must be disabled — our services
            # use manual telemetry only.  Active instrumentors (especially
            # azure_sdk and urllib3) create metric time-series that accumulate
            # without bound and cause growing CPU usage.
            for lib in ("azure_sdk", "django", "fastapi", "flask",
                        "psycopg2", "requests", "urllib", "urllib3"):
                self.assertFalse(
                    opts[lib]["enabled"],
                    f"Auto-instrumentor '{lib}' should be disabled",
                )

    @patch.dict(
        "os.environ",
        {"APPLICATIONINSIGHTS_CONNECTION_STRING": "InstrumentationKey=fake-key;IngestionEndpoint=https://example.com"},
        clear=True,
    )
    def test_configure_otel_sets_disabled_instrumentations_env_var(self) -> None:
        with patch("otel_lib.otel.configure_azure_monitor"):
            configure_otel("test-service")
        self.assertEqual(
            otel_module.os.environ["OTEL_PYTHON_DISABLED_INSTRUMENTATIONS"],
            "azure_sdk,django,fastapi,flask,psycopg2,requests,urllib,urllib3",
        )

    @patch.dict(
        "os.environ",
        {
            "APPLICATIONINSIGHTS_CONNECTION_STRING": "InstrumentationKey=fake-key;IngestionEndpoint=https://example.com",
            "OTEL_PYTHON_DISABLED_INSTRUMENTATIONS": "custom,psycopg2",
        },
        clear=True,
    )
    def test_configure_otel_merges_existing_disabled_instrumentations_env_var(self) -> None:
        with patch("otel_lib.otel.configure_azure_monitor"):
            configure_otel("test-service")
        self.assertEqual(
            otel_module.os.environ["OTEL_PYTHON_DISABLED_INSTRUMENTATIONS"],
            "custom,psycopg2,azure_sdk,django,fastapi,flask,requests,urllib,urllib3",
        )

    @patch.dict(
        "os.environ",
        {"APPLICATIONINSIGHTS_CONNECTION_STRING": "InstrumentationKey=fake-key"},
        clear=True,
    )
    def test_configure_otel_azure_monitor_failure_falls_back_to_noop(self) -> None:
        with patch.object(otel_module, "configure_azure_monitor", side_effect=Exception("boom")):
            configure_otel("test-service")
        provider = trace.get_tracer_provider()
        self.assertIsInstance(provider, TracerProvider)

    @patch.dict("os.environ", {}, clear=True)
    def test_configure_otel_installs_log_filter(self) -> None:
        configure_otel("test-service")
        root_logger = logging.getLogger()
        filter_types = [type(f) for f in root_logger.filters]
        self.assertIn(OtelCorrelationFilter, filter_types)

    @patch.dict("os.environ", {}, clear=True)
    def test_configure_otel_does_not_duplicate_log_filter(self) -> None:
        configure_otel("test-service")
        configure_otel("test-service")
        root_logger = logging.getLogger()
        otel_filters = [f for f in root_logger.filters if isinstance(f, OtelCorrelationFilter)]
        self.assertEqual(len(otel_filters), 1)

    def test_is_configured_false_before_configure(self) -> None:
        self.assertFalse(is_configured())

    @patch.dict("os.environ", {}, clear=True)
    def test_is_configured_true_after_configure(self) -> None:
        configure_otel("test-service")
        self.assertTrue(is_configured())

    @patch.dict(
        "os.environ",
        {"APPLICATIONINSIGHTS_CONNECTION_STRING": "InstrumentationKey=fake-key;IngestionEndpoint=https://example.com"},
        clear=True,
    )
    def test_configure_otel_guard_prevents_double_azure_monitor_call(self) -> None:
        with patch("otel_lib.otel.configure_azure_monitor") as mock_configure:
            configure_otel("test-service")
            configure_otel("test-service-again")
            mock_configure.assert_called_once()

    @patch.dict(
        "os.environ",
        {
            "APPLICATIONINSIGHTS_CONNECTION_STRING": "InstrumentationKey=fake-key;IngestionEndpoint=https://example.com",
            "INSIGHTS_UAMI_CLIENT_ID": "uami-client-id",
        },
        clear=True,
    )
    def test_configure_otel_with_uami_uses_managed_identity_credential(self) -> None:
        with patch("otel_lib.otel.configure_azure_monitor") as mock_configure, \
             patch("otel_lib.otel.ManagedIdentityCredential") as mock_mi_credential:
            configure_otel("test-service")
            _, kwargs = mock_configure.call_args
            self.assertEqual(kwargs["credential"], mock_mi_credential.return_value)

    @patch.dict(
        "os.environ",
        {
            "APPLICATIONINSIGHTS_CONNECTION_STRING": "InstrumentationKey=fake-key;IngestionEndpoint=https://example.com",
            "INSIGHTS_UAMI_CLIENT_ID": "   ",
        },
        clear=True,
    )
    def test_configure_otel_with_blank_uami_falls_back_to_default_credential(self) -> None:
        with patch("otel_lib.otel.configure_azure_monitor") as mock_configure, \
             patch("otel_lib.otel.DefaultAzureCredential") as mock_default_credential:
            configure_otel("test-service")
            _, kwargs = mock_configure.call_args
            self.assertEqual(kwargs["credential"], mock_default_credential.return_value)

    @patch.dict("os.environ", {}, clear=True)
    def test_configure_otel_sets_service_name(self) -> None:
        captured: list[TracerProvider] = []
        original_set = trace.set_tracer_provider

        def capture_provider(p: TracerProvider) -> None:
            captured.append(p)
            original_set(p)

        with patch("otel_lib.otel.trace") as mock_trace:
            mock_trace.set_tracer_provider.side_effect = capture_provider
            mock_trace.get_tracer = trace.get_tracer
            _configure_noop("my-service", "2.0.0")

        self.assertEqual(len(captured), 1)
        resource = captured[0].resource
        self.assertEqual(resource.attributes.get("service.name"), "my-service")
        self.assertEqual(resource.attributes.get("service.version"), "2.0.0")


class TestGetTracer(unittest.TestCase):

    def test_get_tracer_returns_tracer(self) -> None:
        tracer = get_tracer("test.module")
        self.assertIsNotNone(tracer)

    def test_get_tracer_different_names(self) -> None:
        tracer1 = get_tracer("module.a")
        tracer2 = get_tracer("module.b")
        self.assertIsNotNone(tracer1)
        self.assertIsNotNone(tracer2)


class TestInjectExtractTraceContext(unittest.TestCase):

    def setUp(self) -> None:
        otel_module._otel_configured = False
        logging.getLogger().filters = []

    def tearDown(self) -> None:
        otel_module._otel_configured = False
        logging.getLogger().filters = []

    @patch.dict("os.environ", {}, clear=True)
    def test_inject_adds_traceparent_key(self) -> None:
        configure_otel("test-service")
        tracer = get_tracer(__name__)
        with tracer.start_as_current_span("test-span"):
            props = inject_trace_context({})
        self.assertIn("traceparent", props)

    @patch.dict("os.environ", {}, clear=True)
    def test_inject_does_not_mutate_input(self) -> None:
        configure_otel("test-service")
        tracer = get_tracer(__name__)
        original = {"key": "value"}
        with tracer.start_as_current_span("test-span"):
            result = inject_trace_context(original)
        self.assertNotIn("traceparent", original)
        self.assertIn("key", result)

    @patch.dict("os.environ", {}, clear=True)
    def test_extract_returns_context(self) -> None:
        configure_otel("test-service")
        tracer = get_tracer(__name__)
        with tracer.start_as_current_span("root"):
            injected = inject_trace_context({})
        ctx = extract_trace_context(injected)
        self.assertIsNotNone(ctx)

    @patch.dict("os.environ", {}, clear=True)
    def test_extract_empty_dict_returns_empty_context(self) -> None:
        ctx = extract_trace_context({})
        self.assertIsNotNone(ctx)

    @patch.dict("os.environ", {}, clear=True)
    def test_inject_extract_round_trip_preserves_trace_id(self) -> None:
        configure_otel("test-service")
        tracer = get_tracer(__name__)
        with tracer.start_as_current_span("root") as span:
            original_trace_id = span.get_span_context().trace_id
            injected = inject_trace_context({})

        ctx = extract_trace_context(injected)
        span_ctx = trace.get_current_span(ctx).get_span_context()
        self.assertEqual(span_ctx.trace_id, original_trace_id)


class TestOtelCorrelationFilter(unittest.TestCase):

    def setUp(self) -> None:
        otel_module._otel_configured = False
        logging.getLogger().filters = []

    def tearDown(self) -> None:
        otel_module._otel_configured = False
        logging.getLogger().filters = []

    @patch.dict("os.environ", {}, clear=True)
    def test_filter_attaches_zeroed_ids_when_no_active_span(self) -> None:
        f = OtelCorrelationFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        f.filter(record)
        self.assertEqual(record.otel_trace_id, "0" * 32)  # type: ignore[attr-defined]
        self.assertEqual(record.otel_span_id, "0" * 16)  # type: ignore[attr-defined]

    @patch.dict("os.environ", {}, clear=True)
    def test_filter_attaches_real_ids_within_span(self) -> None:
        configure_otel("test-service")
        tracer = get_tracer(__name__)
        f = OtelCorrelationFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        with tracer.start_as_current_span("test-span") as span:
            f.filter(record)
            ctx = span.get_span_context()
            expected_trace_id = format(ctx.trace_id, "032x")
            expected_span_id = format(ctx.span_id, "016x")
        self.assertEqual(record.otel_trace_id, expected_trace_id)  # type: ignore[attr-defined]
        self.assertEqual(record.otel_span_id, expected_span_id)  # type: ignore[attr-defined]

    def test_filter_always_returns_true(self) -> None:
        f = OtelCorrelationFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        result = f.filter(record)
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
