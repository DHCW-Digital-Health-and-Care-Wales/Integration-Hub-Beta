"""Unit tests for Alarm 1 (inactivity) service logic.

Currently covers:
  - _send_alarm_email(): must not log an ERROR when send_alert_email() returns
    False for the expected reason that ALERT_EMAIL_ENABLED is globally off.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

from azure.monitor.query import LogsQueryStatus

from dashboard.services import alarm1
from dashboard.services.alarm1 import _send_alarm_email, get_last_message_times_by_workflow

NOW = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
LAST_MSG_30_AGO = datetime(2026, 6, 22, 11, 30, tzinfo=timezone.utc)


class TestSendAlarmEmail:
    """_send_alarm_email() must not log an ERROR when send_alert_email() returns False
    for the intentional/expected reason that ALERT_EMAIL_ENABLED is globally off — that
    is not a failure, and send_alert_email() logs nothing itself in that case."""

    def test_no_error_log_when_alert_email_globally_disabled(self, caplog: Any) -> None:
        with (
            patch("dashboard.services.alarm1.send_alert_email", return_value=False),
            patch("dashboard.services.alarm1.config.ALERT_EMAIL_ENABLED", False),
            caplog.at_level("WARNING", logger="dashboard.services.alarm1"),
        ):
            _send_alarm_email(
                "rid", "phw-to-mpi", "PHW to MPI", 30.0, 15, LAST_MSG_30_AGO, NOW, email_alerts_enabled=True
            )
        assert not any(r.levelname == "ERROR" for r in caplog.records)
        assert not any("Failed to send alarm 1 email" in r.message for r in caplog.records)

    def test_warning_log_when_send_fails_with_email_enabled(self, caplog: Any) -> None:
        with (
            patch("dashboard.services.alarm1.send_alert_email", return_value=False),
            patch("dashboard.services.alarm1.config.ALERT_EMAIL_ENABLED", True),
            caplog.at_level("WARNING", logger="dashboard.services.alarm1"),
        ):
            _send_alarm_email(
                "rid", "phw-to-mpi", "PHW to MPI", 30.0, 15, LAST_MSG_30_AGO, NOW, email_alerts_enabled=True
            )
        assert any(
            r.levelname == "WARNING" and "Failed to send alarm 1 email" in r.message for r in caplog.records
        )

    def test_async_send_returns_without_blocking(self) -> None:
        started = threading.Event()
        release = threading.Event()
        finished = threading.Event()

        def _slow_send(*_args: object, **_kwargs: object) -> bool:
            started.set()
            release.wait(timeout=2.0)
            finished.set()
            return True

        with patch("dashboard.services.alarm1.send_alert_email", side_effect=_slow_send):
            _send_alarm_email(
                "rid",
                "phw-to-mpi",
                "PHW to MPI",
                30.0,
                15,
                LAST_MSG_30_AGO,
                NOW,
                email_alerts_enabled=True,
                async_send=True,
            )
            # Call returned while background email is still waiting on `release`.
            assert started.wait(timeout=2.0)
            assert not finished.is_set()
            release.set()
            assert finished.wait(timeout=2.0)


class TestGetLastMessageTimesTwoStage:
    """Two-stage lookback avoids scanning 30 days of AppTraces for active workflows."""

    @staticmethod
    def _response(rows: list[list[object]]) -> SimpleNamespace:
        table = SimpleNamespace(columns=["workflow_id", "last_message"], rows=rows)
        return SimpleNamespace(status=LogsQueryStatus.SUCCESS, tables=[table])

    def test_skips_30d_fallback_when_all_workflows_found_in_fast_window(self) -> None:
        mock_client = MagicMock()
        mock_client.query_workspace.return_value = self._response(
            [
                ["phw-to-mpi", LAST_MSG_30_AGO],
                ["chemo-to-mpi", NOW],
            ]
        )

        with (
            patch.object(alarm1.config, "AZURE_LOG_ANALYTICS_WORKSPACE_ID", "ws-1"),
            patch("dashboard.services.alarm1._get_logs_client", return_value=mock_client),
        ):
            result = get_last_message_times_by_workflow(["phw-to-mpi", "chemo-to-mpi"])

        assert result == {"phw-to-mpi": LAST_MSG_30_AGO, "chemo-to-mpi": NOW}
        mock_client.query_workspace.assert_called_once()
        kwargs = mock_client.query_workspace.call_args.kwargs
        assert kwargs["timespan"] == timedelta(days=alarm1._FAST_LOOKBACK_DAYS)
        query = kwargs["query"]
        assert 'Properties has "MESSAGE_RECEIVED"' in query
        assert "Properties has_any (" in query
        assert query.index('Properties has "MESSAGE_RECEIVED"') < query.index("parse_json(Properties)")

    def test_queries_30d_fallback_only_for_missing_workflows(self) -> None:
        older = datetime(2026, 6, 10, 9, 0, tzinfo=timezone.utc)
        mock_client = MagicMock()
        mock_client.query_workspace.side_effect = [
            self._response([["phw-to-mpi", LAST_MSG_30_AGO]]),
            self._response([["quiet-flow", older]]),
        ]

        with (
            patch.object(alarm1.config, "AZURE_LOG_ANALYTICS_WORKSPACE_ID", "ws-1"),
            patch("dashboard.services.alarm1._get_logs_client", return_value=mock_client),
        ):
            result = get_last_message_times_by_workflow(["phw-to-mpi", "quiet-flow"])

        assert result == {"phw-to-mpi": LAST_MSG_30_AGO, "quiet-flow": older}
        assert mock_client.query_workspace.call_count == 2
        fallback_kwargs = mock_client.query_workspace.call_args_list[1].kwargs
        assert fallback_kwargs["timespan"] == timedelta(days=alarm1._FULL_LOOKBACK_DAYS)
        assert '"quiet-flow"' in fallback_kwargs["query"]
        assert '"phw-to-mpi"' not in fallback_kwargs["query"]
