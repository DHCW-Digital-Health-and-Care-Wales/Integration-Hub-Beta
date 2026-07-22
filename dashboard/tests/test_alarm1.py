"""Unit tests for Alarm 1 (inactivity) service logic.

Currently covers:
  - _send_alarm_email(): must not log an ERROR when send_alert_email() returns
    False for the expected reason that ALERT_EMAIL_ENABLED is globally off.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

from dashboard.services.alarm1 import _send_alarm_email

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
