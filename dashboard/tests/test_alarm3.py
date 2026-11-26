"""Unit tests for Alarm 3 (message processing failures) service logic.

Currently covers:
  - _send_alarm3_email(): must not log an ERROR when send_alert_email() returns
    False for the expected reason that ALERT_EMAIL_ENABLED is globally off.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

from azure.monitor.query import LogsQueryStatus

from dashboard.services import alarm3
from dashboard.services.alarm3 import _send_alarm3_email, get_failure_counts

NOW = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)


class TestSendAlarm3Email:
    """_send_alarm3_email() must not log an ERROR when send_alert_email() returns False
    for the intentional/expected reason that ALERT_EMAIL_ENABLED is globally off — that
    is not a failure, and send_alert_email() logs nothing itself in that case."""

    def test_no_error_log_when_alert_email_globally_disabled(self, caplog: Any) -> None:
        with (
            patch("dashboard.services.alarm3.send_alert_email", return_value=False),
            patch("dashboard.services.alarm3.config.ALERT_EMAIL_ENABLED", False),
            caplog.at_level("WARNING", logger="dashboard.services.alarm3"),
        ):
            _send_alarm3_email(
                "rid", "PHW to MPI", 5, 1, 15, "phw-to-mpi", NOW, email_alerts_enabled=True
            )
        assert not any(r.levelname == "ERROR" for r in caplog.records)
        assert not any("Failed to send alarm 3 email" in r.message for r in caplog.records)

    def test_warning_log_when_send_fails_with_email_enabled(self, caplog: Any) -> None:
        with (
            patch("dashboard.services.alarm3.send_alert_email", return_value=False),
            patch("dashboard.services.alarm3.config.ALERT_EMAIL_ENABLED", True),
            caplog.at_level("WARNING", logger="dashboard.services.alarm3"),
        ):
            _send_alarm3_email(
                "rid", "PHW to MPI", 5, 1, 15, "phw-to-mpi", NOW, email_alerts_enabled=True
            )
        assert any(
            r.levelname == "WARNING" and "Failed to send alarm 3 email" in r.message for r in caplog.records
        )


class TestGetFailureCounts:
    def test_kql_prefilters_and_parses_json_once(self) -> None:
        table = SimpleNamespace(columns=["workflow_id", "Total"], rows=[["phw-to-mpi", 4]])
        mock_client = MagicMock()
        mock_client.query_workspace.return_value = SimpleNamespace(status=LogsQueryStatus.SUCCESS, tables=[table])
        rules = [{"id": "r1", "workflow_id": "phw-to-mpi", "window_duration_minutes": 15}]

        with (
            patch.object(alarm3.config, "AZURE_LOG_ANALYTICS_WORKSPACE_ID", "ws-1"),
            patch("dashboard.services.alarm3._get_logs_client", return_value=mock_client),
        ):
            counts = get_failure_counts(rules)

        assert counts == {"r1": 4}
        query = mock_client.query_workspace.call_args.kwargs["query"]
        assert 'Properties has "MESSAGE_FAILED"' in query
        assert 'Properties has_any ("phw-to-mpi")' in query
        assert query.count("parse_json(Properties)") == 1
        assert query.index('Properties has "MESSAGE_FAILED"') < query.index("parse_json(Properties)")

    def test_distinct_windows_are_queried_concurrently(self) -> None:
        barrier = threading.Barrier(2, timeout=2.0)

        def _query_workspace(**kwargs: Any) -> SimpleNamespace:
            barrier.wait()  # Proves both window buckets run in parallel.
            if "ago(15m)" in kwargs["query"]:
                table = SimpleNamespace(columns=["workflow_id", "Total"], rows=[["phw-to-mpi", 2]])
            else:
                table = SimpleNamespace(columns=["workflow_id", "Total"], rows=[["chemo-to-mpi", 7]])
            return SimpleNamespace(status=LogsQueryStatus.SUCCESS, tables=[table])

        mock_client = MagicMock()
        mock_client.query_workspace.side_effect = _query_workspace
        rules = [
            {"id": "r1", "workflow_id": "phw-to-mpi", "window_duration_minutes": 15},
            {"id": "r2", "workflow_id": "chemo-to-mpi", "window_duration_minutes": 60},
        ]

        with (
            patch.object(alarm3.config, "AZURE_LOG_ANALYTICS_WORKSPACE_ID", "ws-1"),
            patch("dashboard.services.alarm3._get_logs_client", return_value=mock_client),
        ):
            counts = get_failure_counts(rules)

        assert counts == {"r1": 2, "r2": 7}
