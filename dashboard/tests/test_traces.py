"""
Tests for dashboard.services.traces.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from azure.monitor.query import LogsQueryStatus

from dashboard.services import traces
from dashboard.services.traces import get_trace


class FakeTable:
    def __init__(self, columns: list[str], rows: list[list[object]]) -> None:
        self.columns = columns
        self.rows = rows


class FakeResponse:
    def __init__(self, tables: list[FakeTable], status: LogsQueryStatus = LogsQueryStatus.SUCCESS) -> None:
        self.status = status
        self.tables = tables
        self.partial_error = None


def _make_client(tables: list[FakeTable], status: LogsQueryStatus = LogsQueryStatus.SUCCESS) -> MagicMock:
    mock = MagicMock()
    mock.query_workspace.return_value = FakeResponse(tables, status)
    return mock


class TestOperationIdValidation(unittest.TestCase):
    def test_rejects_path_traversal(self) -> None:
        result = get_trace("../../etc/passwd")
        self.assertFalse(result["ok"])
        self.assertEqual(result["spans"], [])

    def test_rejects_kql_injection(self) -> None:
        result = get_trace('abc"; drop table AppRequests //')
        self.assertFalse(result["ok"])

    def test_accepts_valid_operation_id(self) -> None:
        with patch.object(traces.config, "AZURE_LOG_ANALYTICS_WORKSPACE_ID", "ws-id"), \
                patch("dashboard.services.traces._get_logs_client") as mock_factory:
            mock_factory.return_value = _make_client([])
            result = get_trace("abc123-DEF_456|xyz")
        # empty because no rows, but the id was accepted (no early return)
        self.assertFalse(result["ok"])
        mock_factory.assert_called_once()

    def test_rejects_empty_string(self) -> None:
        result = get_trace("")
        self.assertFalse(result["ok"])

    def test_rejects_all_zeros_null_trace_id(self) -> None:
        result = get_trace("00000000000000000000000000000000")
        self.assertFalse(result["ok"])
        self.assertEqual(result["spans"], [])


class TestNoWorkspaceConfigured(unittest.TestCase):
    def test_returns_empty_when_workspace_not_set(self) -> None:
        with patch.object(traces.config, "AZURE_LOG_ANALYTICS_WORKSPACE_ID", ""):
            result = get_trace("abc123")
        self.assertFalse(result["ok"])
        self.assertEqual(result["spans"], [])
        self.assertEqual(result["exceptions"], [])
        self.assertEqual(result["logs"], [])


class TestParseSpans(unittest.TestCase):
    def _run(self, rows: list[list[object]]) -> dict:
        columns = [
            "TimeGenerated", "itemType", "name", "duration", "success",
            "resultCode", "target", "parentId", "id", "appName", "severityLevel", "message",
        ]
        table = FakeTable(columns, rows)
        with patch.object(traces.config, "AZURE_LOG_ANALYTICS_WORKSPACE_ID", "ws-id"), \
                patch("dashboard.services.traces._get_logs_client") as mock_factory:
            mock_factory.return_value = _make_client([table])
            return get_trace("op123")

    def test_appRequests_mapped_to_spans(self) -> None:
        ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = self._run([
            [ts, "AppRequests", "POST /api/hl7", 42.5, True, "200",
             "/api/hl7", "parent1", "id1", "phw-transformer", None, ""],
        ])
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["spans"]), 1)
        span = result["spans"][0]
        self.assertEqual(span["name"], "POST /api/hl7")
        self.assertEqual(span["duration"], 42.5)
        self.assertTrue(span["success"])
        self.assertEqual(span["target"], "/api/hl7")
        self.assertEqual(span["app_name"], "phw-transformer")
        self.assertEqual(span["parent_id"], "parent1")

    def test_appDependencies_mapped_to_spans(self) -> None:
        ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = self._run([
            [ts, "AppDependencies", "ServiceBus.Send", 15.0, True, "200",
             "my-queue", "parent2", "id2", "phw-transformer", None, ""],
        ])
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["spans"]), 1)

    def test_appExceptions_mapped_to_exceptions(self) -> None:
        ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = self._run([
            [ts, "AppRequests", "POST /", 10.0, False, "500", "", "", "id0", "app", None, ""],
            [ts, "AppExceptions", "System.NullReferenceException", None, None, None,
             None, None, None, "phw-transformer", 1, "Object ref not set"],
        ])
        self.assertEqual(len(result["exceptions"]), 1)
        exc = result["exceptions"][0]
        self.assertEqual(exc["name"], "System.NullReferenceException")
        self.assertEqual(exc["message"], "Object ref not set")
        self.assertEqual(exc["app_name"], "phw-transformer")

    def test_appTraces_mapped_to_logs(self) -> None:
        ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = self._run([
            [ts, "AppRequests", "GET /health", 5.0, True, "200", "", "", "id0", "app", None, ""],
            [ts, "AppTraces", "Processing HL7 message", None, None, None,
             None, None, None, "phw-transformer", 1, "Processing HL7 message"],
        ])
        self.assertEqual(len(result["logs"]), 1)
        entry = result["logs"][0]
        self.assertEqual(entry["message"], "Processing HL7 message")
        self.assertEqual(entry["severity"], 1)


class TestDurationComputation(unittest.TestCase):
    def test_duration_ms_computed_from_timestamps(self) -> None:
        columns = [
            "TimeGenerated", "itemType", "name", "duration", "success",
            "resultCode", "target", "parentId", "id", "appName", "severityLevel", "message",
        ]
        ts1 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2024, 1, 1, 12, 0, 2, tzinfo=timezone.utc)   # 2 seconds later
        rows = [
            [ts1, "AppRequests", "span-a", 100.0, True, "200", "", "", "id1", "app", None, ""],
            [ts2, "AppDependencies", "span-b", 50.0, True, "200", "", "", "id2", "app", None, ""],
        ]
        table = FakeTable(columns, rows)
        with patch.object(traces.config, "AZURE_LOG_ANALYTICS_WORKSPACE_ID", "ws-id"), \
                patch("dashboard.services.traces._get_logs_client") as mock_factory:
            mock_factory.return_value = _make_client([table])
            result = get_trace("op999")
        self.assertAlmostEqual(result["duration_ms"], 2000.0)
        self.assertIn("2024-01-01", result["start_time"])

    def test_ok_is_false_when_no_spans(self) -> None:
        columns = [
            "TimeGenerated", "itemType", "name", "duration", "success",
            "resultCode", "target", "parentId", "id", "appName", "severityLevel", "message",
        ]
        ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        rows = [
            [ts, "AppTraces", "some log", None, None, None, None, None, None, "app", 1, "some log"],
        ]
        table = FakeTable(columns, rows)
        with patch.object(traces.config, "AZURE_LOG_ANALYTICS_WORKSPACE_ID", "ws-id"), \
                patch("dashboard.services.traces._get_logs_client") as mock_factory:
            mock_factory.return_value = _make_client([table])
            result = get_trace("op000")
        self.assertFalse(result["ok"])


class TestErrorHandling(unittest.TestCase):
    def test_returns_empty_on_client_exception(self) -> None:
        with patch.object(traces.config, "AZURE_LOG_ANALYTICS_WORKSPACE_ID", "ws-id"), \
                patch("dashboard.services.traces._get_logs_client") as mock_factory:
            mock_factory.return_value.query_workspace.side_effect = RuntimeError("network error")
            result = get_trace("abc123")
        self.assertFalse(result["ok"])
        self.assertEqual(result["spans"], [])

    def test_returns_empty_on_failed_query_status(self) -> None:
        table = FakeTable([], [])
        with patch.object(traces.config, "AZURE_LOG_ANALYTICS_WORKSPACE_ID", "ws-id"), \
                patch("dashboard.services.traces._get_logs_client") as mock_factory:
            mock_factory.return_value = _make_client([table], LogsQueryStatus.PARTIAL)
            result = get_trace("abc123")
        self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()
