from __future__ import annotations

from unittest.mock import patch

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

    with patch.object(azure_monitor.config, "AZURE_LOG_ANALYTICS_WORKSPACE_ID", "workspace-id"), \
            patch("dashboard.services.azure_monitor._get_logs_client") as mock_client_factory:
        mock_client_factory.return_value.query_workspace.return_value = FakeResponse([fake_table])

        messages = azure_monitor.get_messages_today()

    assert len(messages) == 1
    assert messages[0]["event"] == "MESSAGE_RECEIVED"
    assert messages[0]["app"] == "uks-dev-mpi-hl7server-ca"
    assert messages[0]["dimensions"]["workflow_id"] == "mpi-to-topic"