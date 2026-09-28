"""
Unit tests for scripts/seed_example_alarms.py — the local-emulator example data seeder.

Only the pure building/merging logic is tested; Cosmos I/O is exercised manually
against the emulator.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from dashboard.services import alarm_pauses
from scripts import seed_example_alarms as seed

FLOWS = ["phw-to-mpi", "paris-to-mpi", "pims-to-mpi", "wds-to-mpi", "chemocare-to-mpi", "mosaiq-to-mpi", "x-to-y"]
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


class TestEnsureLocalEndpoint:
    @pytest.mark.parametrize("endpoint", ["http://localhost:8081", "https://127.0.0.1:8081", "http://cosmos-emulator:8081"])
    def test_local_endpoints_are_allowed(self, endpoint: str) -> None:
        seed.ensure_local_endpoint(endpoint)

    @pytest.mark.parametrize("endpoint", ["", "https://prod-acct.documents.azure.com:443/"])
    def test_missing_or_remote_endpoints_exit(self, endpoint: str) -> None:
        with pytest.raises(SystemExit):
            seed.ensure_local_endpoint(endpoint)


class TestBuildExampleRules:
    def test_one_rule_per_flow_per_alarm_with_module_id_suffixes(self) -> None:
        rules = seed.build_example_rules(FLOWS)
        assert set(rules) == {"alarm1", "alarm2", "alarm3"}
        assert set(rules["alarm1"]) == {f"{f}-inactivity" for f in FLOWS}
        assert set(rules["alarm2"]) == {f"{f}-outgoing" for f in FLOWS}
        assert set(rules["alarm3"]) == {f"{f}-failures" for f in FLOWS}

    def test_rules_have_the_fields_each_alarm_reads(self) -> None:
        rules = seed.build_example_rules(FLOWS)
        a1 = rules["alarm1"]["phw-to-mpi-inactivity"]
        a3 = rules["alarm3"]["phw-to-mpi-failures"]
        assert {"day_threshold_minutes", "evening_threshold_minutes", "weekend_threshold_minutes"} <= set(a1)
        assert {"window_duration_minutes", "threshold"} <= set(a3)
        assert all(r[seed.EXAMPLE_TAG] and r["workflow_id"] for alarm in rules.values() for r in alarm.values())

    def test_mix_of_enabled_disabled_and_email_rules(self) -> None:
        all_rules = [r for alarm in seed.build_example_rules(FLOWS).values() for r in alarm.values()]
        assert any(r["alarm_enabled"] for r in all_rules)
        assert any(not r["alarm_enabled"] for r in all_rules)
        assert any(r["email_alerts_enabled"] for r in all_rules)
        # Email alerts only ever on enabled rules.
        assert not any(r["email_alerts_enabled"] and not r["alarm_enabled"] for r in all_rules)

    def test_output_is_deterministic(self) -> None:
        assert seed.build_example_rules(FLOWS) == seed.build_example_rules(FLOWS)


class TestMergeAndRemove:
    def test_adds_missing_and_keeps_existing(self) -> None:
        cfg = {"rules": {"a": {"display_name": "hand-made"}}}
        added, skipped = seed.merge_rules(cfg, {"a": {"example": True}, "b": {"example": True}}, overwrite=False)
        assert (added, skipped) == (1, 1)
        assert cfg["rules"]["a"] == {"display_name": "hand-made"}

    def test_overwrite_replaces_only_example_rules(self) -> None:
        cfg: dict[str, Any] = {"rules": {"hand": {"display_name": "keep"}, "ex": {"example": True, "threshold": 1}}}
        new: dict[str, dict[str, Any]] = {"hand": {"example": True}, "ex": {"example": True, "threshold": 9}}
        added, skipped = seed.merge_rules(cfg, new, overwrite=True)
        assert (added, skipped) == (1, 1)
        assert cfg["rules"]["hand"] == {"display_name": "keep"}
        assert cfg["rules"]["ex"]["threshold"] == 9

    def test_merge_handles_empty_config(self) -> None:
        cfg: dict = {}
        assert seed.merge_rules(cfg, {"a": {"example": True}}, overwrite=False) == (1, 0)
        assert "a" in cfg["rules"]

    def test_remove_deletes_only_example_rules(self) -> None:
        cfg = {"rules": {"hand": {}, "ex1": {"example": True}, "ex2": {"example": True}}}
        assert seed.remove_example_rules(cfg) == 2
        assert cfg["rules"] == {"hand": {}}


class TestBuildExamplePauses:
    def test_covers_every_pause_status(self) -> None:
        rules = seed.build_example_rules(FLOWS)
        known = {t: {rid: r["workflow_id"] for rid, r in rules[t].items()} for t in rules}
        pauses = seed.build_example_pauses(known, FLOWS, NOW)
        statuses = {alarm_pauses.pause_status(p, NOW) for p in pauses}
        assert statuses == {"active", "scheduled", "ended", "cancelled"}
        assert {p["scope_type"] for p in pauses} == {"rule", "flows", "all"}
        assert any(p["end_at"] is None for p in pauses)
        assert all(p["requested_by"] == seed.EXAMPLE_REQUESTED_BY for p in pauses)
        assert len({p["pause_id"] for p in pauses}) == len(pauses)
