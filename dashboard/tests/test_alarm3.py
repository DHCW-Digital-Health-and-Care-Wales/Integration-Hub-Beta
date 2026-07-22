"""Unit tests for Alarm 3 (message processing failures) service logic.

Currently covers:
  - _send_alarm3_email(): must not log an ERROR when send_alert_email() returns
    False for the expected reason that ALERT_EMAIL_ENABLED is globally off.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

from dashboard.services.alarm3 import _send_alarm3_email

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
