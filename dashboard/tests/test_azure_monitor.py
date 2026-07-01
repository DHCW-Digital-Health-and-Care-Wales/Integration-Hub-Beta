from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from azure.monitor.query import LogsQueryStatus

from dashboard.services import azure_monitor


class FakeResponse:
    def __init__(self, tables: list) -> None:
        self.status = LogsQueryStatus.SUCCESS
        self.tables = tables


class FakeTable:
    def __init__(self, columns: list[str], rows: list[list[object]]) -> None:
        self.columns = columns
        self.rows = rows


def test_parse_dimensions_from_json_string() -> None:
    parsed = azure_monitor._parse_dimensions('{"event_type":"MESSAGE_RECEIVED","microservice_id":"svc"}')

    assert parsed == {"event_type": "MESSAGE_RECEIVED", "microservice_id": "svc"}


def test_get_messages_today_maps_trace_properties() -> None:
    fake_table = FakeTable(
        columns=["timestamp", "name", "customDimensions", "appName"],
        rows=[
            [
                "2026-04-23T11:11:06.2534890Z",
                "Integration Hub Event",
                '{"workflow_id":"mpi-to-topic","microservice_id":"uks-dev-mpi-hl7server-ca","event_type":"MESSAGE_RECEIVED"}',
                "unknown_service",
            ]
        ],
    )

    with (
        patch.object(azure_monitor.config, "AZURE_LOG_ANALYTICS_WORKSPACE_ID", "workspace-id"),
        patch("dashboard.services.azure_monitor._get_logs_client") as mock_client_factory,
    ):
        mock_client_factory.return_value.query_workspace.return_value = FakeResponse([fake_table])

        messages = azure_monitor.get_messages_today()

    assert len(messages) == 1
    assert messages[0]["event"] == "MESSAGE_RECEIVED"
    assert messages[0]["app"] == "uks-dev-mpi-hl7server-ca"
    assert messages[0]["dimensions"]["workflow_id"] == "mpi-to-topic"


def test_get_messages_today_includes_resource_filter() -> None:
    fake_table = FakeTable(columns=["timestamp", "name", "customDimensions", "appName"], rows=[])
    resource_id = "/subscriptions/test/resourceGroups/rg/providers/microsoft.insights/components/appi"

    with (
        patch.object(azure_monitor.config, "AZURE_LOG_ANALYTICS_WORKSPACE_ID", "workspace-id"),
        patch.object(azure_monitor.config, "AZURE_APP_INSIGHTS_RESOURCE_ID", resource_id),
        patch("dashboard.services.azure_monitor._get_logs_client") as mock_client_factory,
    ):
        mock_client_factory.return_value.query_workspace.return_value = FakeResponse([fake_table])
        azure_monitor.get_messages_today()

    query_text = mock_client_factory.return_value.query_workspace.call_args.kwargs["query"]
    assert f"_ResourceId =~ '{resource_id}'" in query_text


def test_get_retry_delay_metrics_by_flow_maps_rows() -> None:
    fake_table = FakeTable(
        columns=["workflow_id", "timestamp", "delay_seconds", "microservice_id", "queue", "attempt"],
        rows=[
            [
                "phw-to-mpi",
                "2026-06-18T12:34:56Z",
                61.0,
                "mpi_hl7_sender",
                "local-inthub-mpi-sender-ingress",
                "3",
            ]
        ],
    )

    with (
        patch.object(azure_monitor.config, "AZURE_LOG_ANALYTICS_WORKSPACE_ID", "workspace-id"),
        patch("dashboard.services.azure_monitor._get_logs_client") as mock_client_factory,
    ):
        mock_client_factory.return_value.query_workspace.return_value = FakeResponse([fake_table])

        rows = azure_monitor.get_retry_delay_metrics_by_flow(hours=24)

    assert len(rows) == 1
    assert rows[0]["workflow_id"] == "phw-to-mpi"
    assert rows[0]["delay_seconds"] == 61.0
    assert rows[0]["attempt"] == 3
    assert rows[0]["queue"] == "local-inthub-mpi-sender-ingress"


def test_get_retry_delay_metrics_by_flow_queries_appmetrics() -> None:
    fake_table = FakeTable(
        columns=["workflow_id", "timestamp", "delay_seconds", "microservice_id", "queue", "attempt"],
        rows=[],
    )

    with (
        patch.object(azure_monitor.config, "AZURE_LOG_ANALYTICS_WORKSPACE_ID", "workspace-id"),
        patch("dashboard.services.azure_monitor._get_logs_client") as mock_client_factory,
    ):
        mock_client_factory.return_value.query_workspace.return_value = FakeResponse([fake_table])

        azure_monitor.get_retry_delay_metrics_by_flow(hours=24)

    query_text = mock_client_factory.return_value.query_workspace.call_args.kwargs["query"]
    assert "AppMetrics" in query_text
    assert "Properties[\"workflow_id\"]" in query_text
    assert "arg_max(TimeGenerated, Sum, microservice_id, queue, attempt)" in query_text
    assert "delay_seconds=todouble(Sum)" in query_text


def test_get_retry_delay_metrics_by_flow_sanitizes_invalid_numeric_inputs() -> None:
    fake_table = FakeTable(
        columns=["workflow_id", "timestamp", "delay_seconds", "microservice_id", "queue", "attempt"],
        rows=[
            ["flow-a", "2026-06-18T12:30:00Z", 75.0, "svc-a", "queue-a", "2"],
        ],
    )

    with (
        patch.object(azure_monitor.config, "AZURE_LOG_ANALYTICS_WORKSPACE_ID", "workspace-id"),
        patch("dashboard.services.azure_monitor._get_logs_client") as mock_client_factory,
    ):
        mock_client_factory.return_value.query_workspace.return_value = FakeResponse([fake_table])

        rows = azure_monitor.get_retry_delay_metrics_by_flow(hours=-4, min_delay_seconds=float("nan"))

    assert len(rows) == 1
    query_text = mock_client_factory.return_value.query_workspace.call_args.kwargs["query"]
    assert "ago(1h)" in query_text
    assert "delay_seconds > 60.0" in query_text
    assert (
        mock_client_factory.return_value.query_workspace.call_args.kwargs["timespan"]
        == azure_monitor.timedelta(hours=1)
    )


def test_get_retry_delay_metrics_by_flow_returns_empty_when_workspace_missing() -> None:
    with patch.object(azure_monitor.config, "AZURE_LOG_ANALYTICS_WORKSPACE_ID", ""):
        rows = azure_monitor.get_retry_delay_metrics_by_flow(hours=24)
    assert rows == []


def test_get_retry_delay_metrics_by_flow_filters_threshold_strictly_greater_than_minimum() -> None:
    fake_table = FakeTable(
        columns=["workflow_id", "timestamp", "delay_seconds", "microservice_id", "queue", "attempt"],
        rows=[
            ["flow-a", "2026-06-18T12:30:00Z", 60.0, "svc-a", "queue-a", "2"],
            ["flow-b", "2026-06-18T12:31:00Z", 61.0, "svc-b", "queue-b", "3"],
        ],
    )

    with (
        patch.object(azure_monitor.config, "AZURE_LOG_ANALYTICS_WORKSPACE_ID", "workspace-id"),
        patch("dashboard.services.azure_monitor._get_logs_client") as mock_client_factory,
    ):
        mock_client_factory.return_value.query_workspace.return_value = FakeResponse([fake_table])

        rows = azure_monitor.get_retry_delay_metrics_by_flow(hours=1, min_delay_seconds=60)

    assert len(rows) == 1
    assert rows[0]["workflow_id"] == "flow-b"
    assert rows[0]["delay_seconds"] == 61.0


# ---------------------------------------------------------------------------
# get_container_app_metric_history tests
# ---------------------------------------------------------------------------


def _make_metric_response(cpu_points: list[dict], mem_points: list[dict]) -> dict:
    """Build a minimal Azure Monitor metrics REST response."""
    return {
        "value": [
            {
                "name": {"value": "CpuPercentage"},
                "timeseries": [{"data": cpu_points}],
            },
            {
                "name": {"value": "WorkingSetBytes"},
                "timeseries": [{"data": mem_points}],
            },
        ]
    }


class TestGetContainerAppMetricHistoryValidation:
    def test_empty_name_returns_empty(self) -> None:
        result = azure_monitor.get_container_app_metric_history("", hours=1)
        assert result == {"name": "", "timestamps": [], "cpu": [], "memory_mb": []}

    def test_uppercase_name_returns_empty(self) -> None:
        result = azure_monitor.get_container_app_metric_history("MyApp", hours=1)
        assert result == {"name": "MyApp", "timestamps": [], "cpu": [], "memory_mb": []}

    def test_name_with_slash_returns_empty(self) -> None:
        result = azure_monitor.get_container_app_metric_history("app/name", hours=1)
        assert result == {"name": "app/name", "timestamps": [], "cpu": [], "memory_mb": []}

    def test_name_ending_with_hyphen_returns_empty(self) -> None:
        result = azure_monitor.get_container_app_metric_history("my-app-", hours=1)
        assert result == {"name": "my-app-", "timestamps": [], "cpu": [], "memory_mb": []}

    def test_name_too_long_returns_empty(self) -> None:
        long_name = "a" * 33
        result = azure_monitor.get_container_app_metric_history(long_name, hours=1)
        assert result == {"name": long_name, "timestamps": [], "cpu": [], "memory_mb": []}

    def test_valid_name_passes_validation(self) -> None:
        """A valid name should not return early due to validation (requires Azure config)."""
        with (
            patch.object(azure_monitor.config, "AZURE_SUBSCRIPTION_ID", ""),
            patch.object(azure_monitor.config, "AZURE_CONTAINER_APPS_RESOURCE_GROUP", ""),
        ):
            result = azure_monitor.get_container_app_metric_history("my-app", hours=1)
        # Returns empty because Azure config is missing, not because validation failed.
        assert result["name"] == "my-app"
        assert result["timestamps"] == []


class TestGetContainerAppMetricHistoryIntervalSelection:
    """Verify that the correct aggregation interval is chosen for each window size."""

    def _call_and_capture_url(self, hours: int) -> str:
        """Call the function and return the URL that was requested."""
        fake_resp = MagicMock()
        fake_resp.json.return_value = _make_metric_response([], [])
        fake_resp.raise_for_status.return_value = None

        fake_cred = MagicMock()
        fake_cred.get_token.return_value = MagicMock(token="tok")

        with (
            patch.object(azure_monitor.config, "AZURE_SUBSCRIPTION_ID", "sub-1"),
            patch.object(azure_monitor.config, "AZURE_CONTAINER_APPS_RESOURCE_GROUP", "rg-1"),
            patch("dashboard.services.azure_monitor.get_azure_credential", return_value=fake_cred),
            patch("requests.get", return_value=fake_resp) as mock_get,
        ):
            azure_monitor.get_container_app_metric_history("my-app", hours=hours)
            return mock_get.call_args[0][0]

    def test_1h_uses_pt1m(self) -> None:
        assert "interval=PT1M" in self._call_and_capture_url(1)

    def test_6h_uses_pt5m(self) -> None:
        assert "interval=PT5M" in self._call_and_capture_url(6)

    def test_24h_uses_pt15m(self) -> None:
        assert "interval=PT15M" in self._call_and_capture_url(24)

    def test_168h_uses_pt1h(self) -> None:
        assert "interval=PT1H" in self._call_and_capture_url(168)


class TestGetContainerAppMetricHistoryParsing:
    """Verify Azure Monitor response parsing and timestamp alignment."""

    def _call_with_response(self, api_response: dict, hours: int = 1) -> dict:
        fake_resp = MagicMock()
        fake_resp.json.return_value = api_response
        fake_resp.raise_for_status.return_value = None

        fake_cred = MagicMock()
        fake_cred.get_token.return_value = MagicMock(token="tok")

        with (
            patch.object(azure_monitor.config, "AZURE_SUBSCRIPTION_ID", "sub-1"),
            patch.object(azure_monitor.config, "AZURE_CONTAINER_APPS_RESOURCE_GROUP", "rg-1"),
            patch("dashboard.services.azure_monitor.get_azure_credential", return_value=fake_cred),
            patch("requests.get", return_value=fake_resp),
        ):
            return azure_monitor.get_container_app_metric_history("my-app", hours=hours)

    def test_parses_cpu_and_memory(self) -> None:
        response = _make_metric_response(
            cpu_points=[{"timeStamp": "2024-01-01T00:00:00Z", "average": 25.0}],
            mem_points=[{"timeStamp": "2024-01-01T00:00:00Z", "average": 134217728.0}],
        )
        result = self._call_with_response(response)

        assert result["name"] == "my-app"
        assert result["timestamps"] == ["2024-01-01T00:00:00Z"]
        assert result["cpu"] == [25.0]
        assert result["memory_mb"] == [round(134217728.0 / 1048576, 2)]

    def test_missing_cpu_point_is_none(self) -> None:
        """When a timestamp has memory data but no CPU data, cpu entry should be None."""
        response = _make_metric_response(
            cpu_points=[],
            mem_points=[{"timeStamp": "2024-01-01T00:00:00Z", "average": 104857600.0}],
        )
        result = self._call_with_response(response)

        assert result["timestamps"] == ["2024-01-01T00:00:00Z"]
        assert result["cpu"] == [None]
        assert result["memory_mb"] == [100.0]

    def test_missing_memory_point_is_none(self) -> None:
        """When a timestamp has CPU data but no memory data, memory_mb entry should be None."""
        response = _make_metric_response(
            cpu_points=[{"timeStamp": "2024-01-01T00:00:00Z", "average": 10.0}],
            mem_points=[],
        )
        result = self._call_with_response(response)

        assert result["timestamps"] == ["2024-01-01T00:00:00Z"]
        assert result["cpu"] == [10.0]
        assert result["memory_mb"] == [None]

    def test_datapoints_without_average_are_skipped(self) -> None:
        """Data points with a missing 'average' field should be silently skipped."""
        response = _make_metric_response(
            cpu_points=[{"timeStamp": "2024-01-01T00:00:00Z"}],
            mem_points=[],
        )
        result = self._call_with_response(response)

        assert result["timestamps"] == []
        assert result["cpu"] == []

    def test_timestamps_are_sorted(self) -> None:
        response = _make_metric_response(
            cpu_points=[
                {"timeStamp": "2024-01-01T00:02:00Z", "average": 5.0},
                {"timeStamp": "2024-01-01T00:01:00Z", "average": 3.0},
                {"timeStamp": "2024-01-01T00:00:00Z", "average": 1.0},
            ],
            mem_points=[],
        )
        result = self._call_with_response(response)

        assert result["timestamps"] == [
            "2024-01-01T00:00:00Z",
            "2024-01-01T00:01:00Z",
            "2024-01-01T00:02:00Z",
        ]

    def test_request_error_returns_empty(self) -> None:
        fake_cred = MagicMock()
        fake_cred.get_token.return_value = MagicMock(token="tok")

        with (
            patch.object(azure_monitor.config, "AZURE_SUBSCRIPTION_ID", "sub-1"),
            patch.object(azure_monitor.config, "AZURE_CONTAINER_APPS_RESOURCE_GROUP", "rg-1"),
            patch("dashboard.services.azure_monitor.get_azure_credential", return_value=fake_cred),
            patch("requests.get", side_effect=RuntimeError("network error")),
        ):
            result = azure_monitor.get_container_app_metric_history("my-app", hours=1)

        assert result == {"name": "my-app", "timestamps": [], "cpu": [], "memory_mb": []}


# ---------------------------------------------------------------------------
# get_hl7_throughput_metrics tests
# ---------------------------------------------------------------------------


def test_resolve_throughput_bin_picks_resolution_by_window() -> None:
    assert azure_monitor._resolve_throughput_bin(24) == ("15m", 15)
    assert azure_monitor._resolve_throughput_bin(72) == ("15m", 15)
    assert azure_monitor._resolve_throughput_bin(168) == ("1h", 60)
    assert azure_monitor._resolve_throughput_bin(336) == ("1h", 60)
    assert azure_monitor._resolve_throughput_bin(720) == ("6h", 360)


def test_get_hl7_throughput_returns_empty_when_workspace_missing() -> None:
    with patch.object(azure_monitor.config, "AZURE_LOG_ANALYTICS_WORKSPACE_ID", ""):
        result = azure_monitor.get_hl7_throughput_metrics(hours=24)
    assert result == {"incoming": [], "outgoing": [], "timespan": "24h", "bin_minutes": 15}


def test_get_hl7_throughput_maps_both_series() -> None:
    now = datetime.now(timezone.utc)
    fake_table = FakeTable(
        columns=["TimeGenerated", "Name", "Value"],
        rows=[
            [now, "messages_received", 12.0],
            [now, "messages_sent", 8.0],
        ],
    )

    with (
        patch.object(azure_monitor.config, "AZURE_LOG_ANALYTICS_WORKSPACE_ID", "workspace-id"),
        patch("dashboard.services.azure_monitor._get_logs_client") as mock_client_factory,
    ):
        mock_client_factory.return_value.query_workspace.return_value = FakeResponse([fake_table])

        result = azure_monitor.get_hl7_throughput_metrics(hours=24)

    assert result["timespan"] == "24h"
    assert result["bin_minutes"] == 15
    # Zero-filling fills quiet bins with 0, so each series sums to its single point.
    assert sum(p["value"] for p in result["incoming"]) == 12
    assert sum(p["value"] for p in result["outgoing"]) == 8


def test_get_hl7_throughput_sanitises_filters() -> None:
    captured: dict = {}

    def _capture(**kwargs: object) -> FakeResponse:
        captured["query"] = kwargs.get("query")
        return FakeResponse([])

    with (
        patch.object(azure_monitor.config, "AZURE_LOG_ANALYTICS_WORKSPACE_ID", "workspace-id"),
        patch("dashboard.services.azure_monitor._get_logs_client") as mock_client_factory,
    ):
        mock_client_factory.return_value.query_workspace.side_effect = _capture

        azure_monitor.get_hl7_throughput_metrics(
            hours=24,
            health_board='PHW"; drop',
            service="phw-to-mpi",
        )

    query = captured["query"]
    # Injection characters are stripped; only the safe characters survive.
    assert 'Properties["health_board"]) == "PHWdrop"' in query
    assert 'Properties["workflow_id"]) == "phw-to-mpi"' in query


def test_get_throughput_filter_options_maps_distinct_values() -> None:
    fake_table = FakeTable(
        columns=["health_board", "workflow_id"],
        rows=[
            ["PHW", "phw-to-mpi"],
            ["SBU", "chemo-to-mpi"],
            ["PHW", "phw-to-mpi"],
            ["", ""],
        ],
    )

    with (
        patch.object(azure_monitor.config, "AZURE_LOG_ANALYTICS_WORKSPACE_ID", "workspace-id"),
        patch("dashboard.services.azure_monitor._get_logs_client") as mock_client_factory,
    ):
        mock_client_factory.return_value.query_workspace.return_value = FakeResponse([fake_table])

        result = azure_monitor.get_throughput_filter_options()

    assert result == {
        "health_boards": ["PHW", "SBU"],
        "services": ["chemo-to-mpi", "phw-to-mpi"],
    }


def test_get_throughput_filter_options_returns_empty_when_workspace_missing() -> None:
    with patch.object(azure_monitor.config, "AZURE_LOG_ANALYTICS_WORKSPACE_ID", ""):
        result = azure_monitor.get_throughput_filter_options()
    assert result == {"health_boards": [], "services": []}
