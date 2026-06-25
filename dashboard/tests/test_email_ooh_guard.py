"""Unit tests for the Email OOH guard on alarm config POST handlers.

Covers the fix that forces ``email_ooh_enabled`` to ``False`` whenever
``email_alerts_enabled`` is ``False``, applied in all three alarm config
routes (Alarm 1 / Alarm 2 / Alarm 3).

The guard exists in two places:
  1. Frontend JS – unchecks the OOH toggle when Email is toggled off so the
     browser never submits a stale checked-but-hidden value.
  2. Backend (app.py POST handlers) – defensive ``and email_alerts_enabled``
     guard that enforces the invariant server-side regardless of form input.

These tests cover the backend layer only (the JS layer is not exercised in
Python unit tests).  The key scenario is: OOH checkbox value IS present in
the submitted form (simulating the pre-fix bug where a checked-but-hidden
checkbox was still submitted), but Email toggle is NOT present (unchecked).
The saved config must show ``email_ooh_enabled = False``.
"""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from flask.testing import FlaskClient

from dashboard import app as app_module

app = app_module.app

# A rule ID used across all test classes.
RID = "phw-to-mpi-outgoing"


# ---------------------------------------------------------------------------
# Shared client fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def client() -> Generator[FlaskClient, None, None]:
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers – build minimal valid form payloads for each alarm type
# ---------------------------------------------------------------------------


def _alarm1_form(rid: str, *, email: bool, email_ooh: bool) -> dict:
    """Minimal form payload for /alarm-config (Alarm 1 — inactivity)."""
    data: dict = {
        f"alerting_gap_{rid}": "60",
        f"day_threshold_{rid}": "60",
        f"evening_threshold_{rid}": "120",
        f"weekend_threshold_{rid}": "240",
        f"workflow_id_{rid}": "phw-to-mpi",
        f"display_name_{rid}": "PHW to MPI",
    }
    if email:
        data[f"email_{rid}"] = "on"
    if email_ooh:
        # Simulate a checked-but-hidden OOH checkbox still being submitted.
        data[f"email_ooh_{rid}"] = "on"
    return data


def _alarm2_form(rid: str, *, email: bool, email_ooh: bool) -> dict:
    """Minimal form payload for /alarm2-config (Alarm 2 — outgoing messages)."""
    data: dict = {
        f"alerting_gap_{rid}": "60",
        f"day_threshold_{rid}": "60",
        f"evening_threshold_{rid}": "120",
        f"weekend_threshold_{rid}": "240",
        f"workflow_id_{rid}": "phw-to-mpi",
        f"display_name_{rid}": "PHW to MPI",
    }
    if email:
        data[f"email_{rid}"] = "on"
    if email_ooh:
        data[f"email_ooh_{rid}"] = "on"
    return data


def _alarm3_form(rid: str, *, email: bool, email_ooh: bool) -> dict:
    """Minimal form payload for /alarm3-config (Alarm 3 — failures)."""
    data: dict = {
        f"alerting_gap_{rid}": "60",
        f"window_duration_{rid}": "15",
        f"threshold_{rid}": "1",
        f"workflow_id_{rid}": "phw-to-mpi",
        f"display_name_{rid}": "PHW to MPI",
    }
    if email:
        data[f"email_{rid}"] = "on"
    if email_ooh:
        data[f"email_ooh_{rid}"] = "on"
    return data


# ---------------------------------------------------------------------------
# Alarm 1  (/alarm-config)
# ---------------------------------------------------------------------------


class TestAlarm1EmailOohGuard:
    """email_ooh_enabled must be False whenever email_alerts_enabled is False."""

    def _post(self, client: FlaskClient, form_data: dict) -> dict:
        """POST to /alarm-config and return the config dict passed to save."""
        mock_save = MagicMock()
        with (
            patch("dashboard.app.load_alarm_config", return_value={"rules": {}}),
            patch("dashboard.app.save_alarm_config", mock_save),
            patch("dashboard.app.get_config_page_data", return_value=[]),
        ):
            resp = client.post("/alarm-config", data=form_data)
        assert resp.status_code == 200
        mock_save.assert_called_once()
        return mock_save.call_args[0][0]

    def test_email_off_ooh_submitted_saves_ooh_false(self, client: FlaskClient) -> None:
        """Core bug scenario: OOH checkbox submitted despite Email being off.

        Before the fix, the hidden-but-checked OOH checkbox would be submitted
        and saved as True.  After the fix the backend guard must force it False.
        """
        cfg = self._post(client, _alarm1_form(RID, email=False, email_ooh=True))
        rule = cfg["rules"][RID]
        assert rule["email_alerts_enabled"] is False
        assert rule["email_ooh_enabled"] is False

    def test_email_on_ooh_on_saves_both_true(self, client: FlaskClient) -> None:
        """When Email is enabled and OOH is checked, both flags are saved True."""
        cfg = self._post(client, _alarm1_form(RID, email=True, email_ooh=True))
        rule = cfg["rules"][RID]
        assert rule["email_alerts_enabled"] is True
        assert rule["email_ooh_enabled"] is True

    def test_email_on_ooh_off_saves_ooh_false(self, client: FlaskClient) -> None:
        """Email on, OOH unchecked → OOH saved as False."""
        cfg = self._post(client, _alarm1_form(RID, email=True, email_ooh=False))
        rule = cfg["rules"][RID]
        assert rule["email_alerts_enabled"] is True
        assert rule["email_ooh_enabled"] is False

    def test_email_off_ooh_off_saves_both_false(self, client: FlaskClient) -> None:
        """Both unchecked → both saved as False."""
        cfg = self._post(client, _alarm1_form(RID, email=False, email_ooh=False))
        rule = cfg["rules"][RID]
        assert rule["email_alerts_enabled"] is False
        assert rule["email_ooh_enabled"] is False


# ---------------------------------------------------------------------------
# Alarm 2  (/alarm2-config)
# ---------------------------------------------------------------------------


class TestAlarm2EmailOohGuard:
    """Same OOH guard contract on the Alarm 2 (outgoing messages) config route."""

    def _post(self, client: FlaskClient, form_data: dict) -> dict:
        mock_save = MagicMock()
        with (
            patch("dashboard.app.load_alarm2_config", return_value={"rules": {}}),
            patch("dashboard.app.save_alarm2_config", mock_save),
            patch("dashboard.app.get_alarm2_config_page_data", return_value=[]),
        ):
            resp = client.post("/alarm2-config", data=form_data)
        assert resp.status_code == 200
        mock_save.assert_called_once()
        return mock_save.call_args[0][0]

    def test_email_off_ooh_submitted_saves_ooh_false(self, client: FlaskClient) -> None:
        """Core bug scenario: OOH submitted while Email is off — must save False."""
        cfg = self._post(client, _alarm2_form(RID, email=False, email_ooh=True))
        rule = cfg["rules"][RID]
        assert rule["email_alerts_enabled"] is False
        assert rule["email_ooh_enabled"] is False

    def test_email_on_ooh_on_saves_both_true(self, client: FlaskClient) -> None:
        cfg = self._post(client, _alarm2_form(RID, email=True, email_ooh=True))
        rule = cfg["rules"][RID]
        assert rule["email_alerts_enabled"] is True
        assert rule["email_ooh_enabled"] is True

    def test_email_on_ooh_off_saves_ooh_false(self, client: FlaskClient) -> None:
        cfg = self._post(client, _alarm2_form(RID, email=True, email_ooh=False))
        rule = cfg["rules"][RID]
        assert rule["email_alerts_enabled"] is True
        assert rule["email_ooh_enabled"] is False

    def test_email_off_ooh_off_saves_both_false(self, client: FlaskClient) -> None:
        cfg = self._post(client, _alarm2_form(RID, email=False, email_ooh=False))
        rule = cfg["rules"][RID]
        assert rule["email_alerts_enabled"] is False
        assert rule["email_ooh_enabled"] is False


# ---------------------------------------------------------------------------
# Alarm 3  (/alarm3-config)
# ---------------------------------------------------------------------------


class TestAlarm3EmailOohGuard:
    """Same OOH guard contract on the Alarm 3 (failures) config route."""

    def _post(self, client: FlaskClient, form_data: dict) -> dict:
        mock_save = MagicMock()
        with (
            patch("dashboard.app.load_alarm3_config", return_value={"rules": {}}),
            patch("dashboard.app.save_alarm3_config", mock_save),
            patch("dashboard.app.get_alarm3_config_page_data", return_value=[]),
        ):
            resp = client.post("/alarm3-config", data=form_data)
        assert resp.status_code == 200
        mock_save.assert_called_once()
        return mock_save.call_args[0][0]

    def test_email_off_ooh_submitted_saves_ooh_false(self, client: FlaskClient) -> None:
        """Core bug scenario: OOH submitted while Email is off — must save False."""
        cfg = self._post(client, _alarm3_form(RID, email=False, email_ooh=True))
        rule = cfg["rules"][RID]
        assert rule["email_alerts_enabled"] is False
        assert rule["email_ooh_enabled"] is False

    def test_email_on_ooh_on_saves_both_true(self, client: FlaskClient) -> None:
        cfg = self._post(client, _alarm3_form(RID, email=True, email_ooh=True))
        rule = cfg["rules"][RID]
        assert rule["email_alerts_enabled"] is True
        assert rule["email_ooh_enabled"] is True

    def test_email_on_ooh_off_saves_ooh_false(self, client: FlaskClient) -> None:
        cfg = self._post(client, _alarm3_form(RID, email=True, email_ooh=False))
        rule = cfg["rules"][RID]
        assert rule["email_alerts_enabled"] is True
        assert rule["email_ooh_enabled"] is False

    def test_email_off_ooh_off_saves_both_false(self, client: FlaskClient) -> None:
        cfg = self._post(client, _alarm3_form(RID, email=False, email_ooh=False))
        rule = cfg["rules"][RID]
        assert rule["email_alerts_enabled"] is False
        assert rule["email_ooh_enabled"] is False
