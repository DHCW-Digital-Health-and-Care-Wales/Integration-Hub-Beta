"""
Unit tests for dashboard.services.alarm_pauses — scheduled alarm pause records.

Covers status transitions over time, scope matching (single rule, flows, all flows),
overlapping pauses, UK-time parsing across clock changes, request validation,
cancel-before/after-start semantics, retention purging and the persistence guards.
Cosmos is mocked throughout; stored documents are mocked in their real shape
(``pause_id`` rather than ``id``, which cosmos_store strips on read).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import patch

import pytest

from dashboard.services import alarm_pauses
from dashboard.services.alarm_pauses import PauseConflictError, PauseError, PauseNotFoundError, PausePersistenceError

# 1 Oct 2026 12:00 UTC == 13:00 BST in London.
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
KNOWN_RULES: dict[str, dict[str, str]] = {
    "alarm1": {"phw-inactivity": "phw-to-mpi", "pims-inactivity": "pims-to-mpi"},
    "alarm2": {"phw-outgoing": "phw-to-mpi"},
    "alarm3": {},
}


def _pause(
    pause_id: str = "p1",
    scope_type: str = "flows",
    targets: list[Any] | None = None,
    start: datetime = NOW - timedelta(hours=1),
    end: datetime | None = NOW + timedelta(hours=1),
    cancelled: datetime | None = None,
) -> dict[str, Any]:
    """Build a stored pause document in the shape list_pauses() returns."""
    return {
        "pause_id": pause_id,
        "scope_type": scope_type,
        "targets": ["phw-to-mpi"] if targets is None else targets,
        "start_at": start.isoformat(),
        "end_at": end.isoformat() if end else None,
        "reason": "Maintenance",
        "requested_by": "Alex",
        "created_at": (start - timedelta(minutes=5)).isoformat(),
        "cancelled_at": cancelled.isoformat() if cancelled else None,
    }


def _payload(**overrides: Any) -> dict[str, Any]:
    """A valid create-pause request body, with overrides."""
    payload: dict[str, Any] = {
        "scope_type": "flows",
        "targets": ["phw-to-mpi"],
        "start": None,
        "end_mode": "duration",
        "duration_minutes": 60,
        "reason": "Planned maintenance",
        "requested_by": "Alex",
    }
    payload.update(overrides)
    return payload


class TestPauseStatus:
    def test_future_start_is_scheduled(self) -> None:
        p = _pause(start=NOW + timedelta(minutes=5))
        assert alarm_pauses.pause_status(p, NOW) == "scheduled"

    def test_started_and_not_ended_is_active(self) -> None:
        assert alarm_pauses.pause_status(_pause(), NOW) == "active"

    def test_start_exactly_now_is_active(self) -> None:
        assert alarm_pauses.pause_status(_pause(start=NOW), NOW) == "active"

    def test_indefinite_pause_stays_active(self) -> None:
        p = _pause(start=NOW - timedelta(days=30), end=None)
        assert alarm_pauses.pause_status(p, NOW) == "active"

    def test_end_reached_is_ended(self) -> None:
        # Edge case: end == now means the pause has just finished (alarms resume).
        assert alarm_pauses.pause_status(_pause(end=NOW), NOW) == "ended"

    def test_cancelled_before_start_is_cancelled(self) -> None:
        p = _pause(start=NOW + timedelta(hours=1), cancelled=NOW - timedelta(minutes=1))
        assert alarm_pauses.pause_status(p, NOW) == "cancelled"

    def test_cancelled_after_start_is_ended(self) -> None:
        p = _pause(end=NOW - timedelta(minutes=1), cancelled=NOW - timedelta(minutes=1))
        assert alarm_pauses.pause_status(p, NOW) == "ended"

    def test_missing_start_is_treated_as_ended(self) -> None:
        # Edge case: a corrupt document must never suppress alarms.
        p = _pause()
        p["start_at"] = None
        assert alarm_pauses.pause_status(p, NOW) == "ended"


class TestCovers:
    def test_all_scope_covers_every_rule(self) -> None:
        p = _pause(scope_type="all", targets=[])
        assert alarm_pauses.covers(p, "alarm3", "anything", "")

    def test_flows_scope_matches_by_workflow_for_every_alarm_type(self) -> None:
        p = _pause(scope_type="flows", targets=["phw-to-mpi"])
        assert alarm_pauses.covers(p, "alarm1", "phw-inactivity", "phw-to-mpi")
        assert alarm_pauses.covers(p, "alarm3", "brand-new-rule", "phw-to-mpi")
        assert not alarm_pauses.covers(p, "alarm1", "pims-inactivity", "pims-to-mpi")

    def test_flows_scope_ignores_rules_without_workflow(self) -> None:
        p = _pause(scope_type="flows", targets=["phw-to-mpi"])
        assert not alarm_pauses.covers(p, "alarm1", "orphan", "")

    def test_rule_scope_matches_alarm_type_and_rule_id(self) -> None:
        targets = [{"alarm_type": "alarm1", "rule_id": "phw-inactivity", "workflow_id": "phw-to-mpi"}]
        p = _pause(scope_type="rule", targets=targets)
        assert alarm_pauses.covers(p, "alarm1", "phw-inactivity", "phw-to-mpi")
        # Same rule id under a different alarm type is a different rule.
        assert not alarm_pauses.covers(p, "alarm2", "phw-inactivity", "phw-to-mpi")
        # Rule scope does not spread to other rules on the same flow.
        assert not alarm_pauses.covers(p, "alarm1", "other", "phw-to-mpi")

    def test_unknown_scope_covers_nothing(self) -> None:
        assert not alarm_pauses.covers(_pause(scope_type="bogus"), "alarm1", "r", "phw-to-mpi")


class TestActiveAndScheduledLookup:
    def test_returns_none_when_nothing_covers_rule(self) -> None:
        assert alarm_pauses.active_pause_for([], "alarm1", "r", "phw-to-mpi", NOW) is None

    def test_ignores_scheduled_and_ended_pauses(self) -> None:
        pauses = [
            _pause("future", start=NOW + timedelta(hours=1)),
            _pause("past", start=NOW - timedelta(hours=2), end=NOW - timedelta(hours=1)),
        ]
        assert alarm_pauses.active_pause_for(pauses, "alarm1", "r", "phw-to-mpi", NOW) is None

    def test_overlap_prefers_latest_end_and_indefinite_wins(self) -> None:
        short = _pause("short", end=NOW + timedelta(minutes=10))
        long = _pause("long", end=NOW + timedelta(hours=5))
        forever = _pause("forever", scope_type="all", targets=[], end=None)
        match = alarm_pauses.active_pause_for([short, long], "alarm1", "r", "phw-to-mpi", NOW)
        assert match is not None and match["pause_id"] == "long"
        match = alarm_pauses.active_pause_for([short, long, forever], "alarm1", "r", "phw-to-mpi", NOW)
        assert match is not None and match["pause_id"] == "forever"

    def test_next_scheduled_returns_soonest(self) -> None:
        later = _pause("later", start=NOW + timedelta(days=2))
        sooner = _pause("sooner", start=NOW + timedelta(hours=3))
        match = alarm_pauses.next_scheduled_for([later, sooner], "alarm1", "r", "phw-to-mpi", NOW)
        assert match is not None and match["pause_id"] == "sooner"


class TestRowHelpers:
    def test_pause_row_fields_for_timed_pause(self) -> None:
        fields = alarm_pauses.pause_row_fields(_pause(end=NOW + timedelta(minutes=90)), NOW)
        assert fields["pause_remaining"] == 90
        assert fields["pause_indefinite"] is False
        assert fields["paused_by"] == "Alex"
        assert fields["pause_scope"] == "flows"
        # Displayed in UK time: 13:30 UTC is 14:30 BST.
        assert fields["paused_until"] == "01 Oct 2026  14:30 BST"

    def test_pause_row_fields_for_indefinite_pause(self) -> None:
        fields = alarm_pauses.pause_row_fields(_pause(end=None), NOW)
        assert fields["pause_remaining"] is None
        assert fields["paused_until"] is None
        assert fields["pause_indefinite"] is True

    def test_annotate_scheduled_marks_only_covered_rows(self) -> None:
        rows = [
            {"id": "phw-inactivity", "workflow_id": "phw-to-mpi"},
            {"id": "pims-inactivity", "workflow_id": "pims-to-mpi"},
        ]
        pauses = [_pause("s1", start=NOW + timedelta(hours=1))]
        alarm_pauses.annotate_scheduled(rows, "alarm1", pauses, NOW)
        assert rows[0]["scheduled_pause"] == {"pause_id": "s1", "start_display": "01 Oct 2026  14:00 BST"}
        assert rows[1]["scheduled_pause"] is None

    def test_summarise_counts_active_and_scheduled(self) -> None:
        pauses = [
            _pause("a"),
            _pause("s", start=NOW + timedelta(hours=1)),
            _pause("e", end=NOW - timedelta(minutes=1)),
        ]
        assert alarm_pauses.summarise(pauses, NOW) == {"active": 1, "scheduled": 1}

    def test_flow_pause_summary_includes_rule_scope_via_stored_workflow(self) -> None:
        rule_pause = _pause(
            "r1",
            scope_type="rule",
            targets=[{"alarm_type": "alarm1", "rule_id": "phw-inactivity", "workflow_id": "phw-to-mpi"}],
        )
        scheduled_all = _pause("all", scope_type="all", targets=[], start=NOW + timedelta(hours=2))
        summary = alarm_pauses.flow_pause_summary([rule_pause, scheduled_all], ["phw-to-mpi", "pims-to-mpi"], NOW)
        assert summary["phw-to-mpi"]["active"]["pause_id"] == "r1"
        assert summary["phw-to-mpi"]["scheduled"]["pause_id"] == "all"
        # The all-flows pause is scheduled for every flow; nothing is active on PIMS.
        assert summary["pims-to-mpi"]["active"] is None
        assert summary["pims-to-mpi"]["scheduled"]["pause_id"] == "all"

    def test_flow_pause_summary_omits_unaffected_flows(self) -> None:
        assert alarm_pauses.flow_pause_summary([_pause()], ["pims-to-mpi"], NOW) == {}


class TestGroupForDisplay:
    def test_groups_and_limits_recent_to_seven_days(self) -> None:
        pauses = [
            _pause("active"),
            _pause("scheduled", start=NOW + timedelta(hours=1)),
            _pause("recent", start=NOW - timedelta(days=2), end=NOW - timedelta(days=1)),
            _pause("old", start=NOW - timedelta(days=20), end=NOW - timedelta(days=10)),
            _pause("cancelled", start=NOW + timedelta(days=1), cancelled=NOW - timedelta(hours=1)),
        ]
        groups = alarm_pauses.group_for_display(pauses, NOW)
        assert [v["pause_id"] for v in groups["active"]] == ["active"]
        assert [v["pause_id"] for v in groups["scheduled"]] == ["scheduled"]
        # Most recently finished first; "old" finished more than 7 days ago.
        assert [v["pause_id"] for v in groups["recent"]] == ["cancelled", "recent"]

    def test_view_flags_early_end(self) -> None:
        p = _pause(end=NOW - timedelta(minutes=5), cancelled=NOW - timedelta(minutes=5))
        view = alarm_pauses.to_view(p, NOW)
        assert view["status"] == "ended"
        assert view["cancelled_early"] is True


class TestParseLondonDatetime:
    def test_bst_input_converted_to_utc(self) -> None:
        assert alarm_pauses.parse_london_datetime("2026-10-01T14:00", "Start") == datetime(
            2026, 10, 1, 13, 0, tzinfo=timezone.utc
        )

    def test_gmt_input_converted_to_utc(self) -> None:
        assert alarm_pauses.parse_london_datetime("2026-12-01T14:00", "Start") == datetime(
            2026, 12, 1, 14, 0, tzinfo=timezone.utc
        )

    def test_spring_forward_gap_is_rejected(self) -> None:
        # 28 Mar 2027 01:30 does not exist in UK time (clocks jump 01:00 -> 02:00).
        with pytest.raises(PauseError, match="does not exist"):
            alarm_pauses.parse_london_datetime("2027-03-28T01:30", "Start time")

    def test_autumn_ambiguous_time_uses_first_occurrence(self) -> None:
        # 25 Oct 2026 01:30 happens twice; the first (BST) occurrence is 00:30 UTC.
        assert alarm_pauses.parse_london_datetime("2026-10-25T01:30", "Start") == datetime(
            2026, 10, 25, 0, 30, tzinfo=timezone.utc
        )

    def test_invalid_input_is_rejected(self) -> None:
        with pytest.raises(PauseError, match="not a valid date"):
            alarm_pauses.parse_london_datetime("tomorrow", "Start time")


class TestBuildPause:
    def test_valid_flows_pause_starting_now(self) -> None:
        pause = alarm_pauses.build_pause(_payload(), KNOWN_RULES, NOW)
        assert pause["scope_type"] == "flows"
        assert pause["targets"] == ["phw-to-mpi"]
        assert pause["start_at"] == NOW.isoformat()
        assert pause["end_at"] == (NOW + timedelta(minutes=60)).isoformat()
        assert pause["cancelled_at"] is None
        assert pause["pause_id"]

    def test_scheduled_start_and_explicit_end(self) -> None:
        pause = alarm_pauses.build_pause(
            _payload(start="2026-10-02T09:00", end_mode="until", end="2026-10-02T11:30"), KNOWN_RULES, NOW
        )
        assert pause["start_at"] == datetime(2026, 10, 2, 8, 0, tzinfo=timezone.utc).isoformat()
        assert pause["end_at"] == datetime(2026, 10, 2, 10, 30, tzinfo=timezone.utc).isoformat()

    def test_indefinite_end(self) -> None:
        assert alarm_pauses.build_pause(_payload(end_mode="indefinite"), KNOWN_RULES, NOW)["end_at"] is None

    def test_start_slightly_in_past_is_clamped_to_now(self) -> None:
        # Edge case: form left open for a minute — 12:59 BST is 1 minute before NOW.
        pause = alarm_pauses.build_pause(_payload(start="2026-10-01T12:59"), KNOWN_RULES, NOW)
        assert pause["start_at"] == NOW.isoformat()

    def test_start_well_in_past_is_rejected(self) -> None:
        with pytest.raises(PauseError, match="in the past"):
            alarm_pauses.build_pause(_payload(start="2026-10-01T10:00"), KNOWN_RULES, NOW)

    def test_start_more_than_a_year_ahead_is_rejected(self) -> None:
        with pytest.raises(PauseError, match="365 days"):
            alarm_pauses.build_pause(_payload(start="2027-12-01T10:00"), KNOWN_RULES, NOW)

    def test_end_before_start_is_rejected(self) -> None:
        with pytest.raises(PauseError, match="after the start"):
            alarm_pauses.build_pause(
                _payload(start="2026-10-02T09:00", end_mode="until", end="2026-10-02T08:00"), KNOWN_RULES, NOW
            )

    @pytest.mark.parametrize("minutes", [0, -5, "abc", None, alarm_pauses.MAX_DURATION_MINUTES + 1])
    def test_invalid_durations_are_rejected(self, minutes: Any) -> None:
        with pytest.raises(PauseError, match="Duration"):
            alarm_pauses.build_pause(_payload(duration_minutes=minutes), KNOWN_RULES, NOW)

    def test_invalid_end_mode_is_rejected(self) -> None:
        with pytest.raises(PauseError, match="end option"):
            alarm_pauses.build_pause(_payload(end_mode="sometime"), KNOWN_RULES, NOW)

    @pytest.mark.parametrize("field", ["reason", "requested_by"])
    @pytest.mark.parametrize("value", [None, "", "   ", 123])
    def test_reason_and_requested_by_are_required(self, field: str, value: Any) -> None:
        with pytest.raises(PauseError, match="required"):
            alarm_pauses.build_pause(_payload(**{field: value}), KNOWN_RULES, NOW)

    def test_overlong_reason_is_rejected(self) -> None:
        with pytest.raises(PauseError, match="too long"):
            alarm_pauses.build_pause(_payload(reason="x" * 201), KNOWN_RULES, NOW)

    def test_invalid_scope_is_rejected(self) -> None:
        with pytest.raises(PauseError, match="scope"):
            alarm_pauses.build_pause(_payload(scope_type="everything"), KNOWN_RULES, NOW)

    @pytest.mark.parametrize("targets", [[], None, "phw-to-mpi"])
    def test_flows_scope_needs_a_target_list(self, targets: Any) -> None:
        with pytest.raises(PauseError, match="at least one"):
            alarm_pauses.build_pause(_payload(targets=targets), KNOWN_RULES, NOW)

    @pytest.mark.parametrize("wid", ["bad id", "phw.to.mpi", "-leading", 42])
    def test_flows_scope_rejects_invalid_workflow_ids(self, wid: Any) -> None:
        with pytest.raises(PauseError, match="Invalid flow id"):
            alarm_pauses.build_pause(_payload(targets=[wid]), KNOWN_RULES, NOW)

    def test_flows_scope_deduplicates_targets(self) -> None:
        pause = alarm_pauses.build_pause(_payload(targets=["phw-to-mpi", " phw-to-mpi "]), KNOWN_RULES, NOW)
        assert pause["targets"] == ["phw-to-mpi"]

    def test_too_many_targets_is_rejected(self) -> None:
        # Edge case: guards against an oversized payload.
        targets = [f"flow-{i}" for i in range(alarm_pauses.MAX_TARGETS + 1)]
        with pytest.raises(PauseError, match="Too many"):
            alarm_pauses.build_pause(_payload(targets=targets), KNOWN_RULES, NOW)

    def test_all_scope_ignores_targets(self) -> None:
        pause = alarm_pauses.build_pause(_payload(scope_type="all", targets=None), KNOWN_RULES, NOW)
        assert pause["targets"] == []

    def test_rule_scope_stores_workflow_id(self) -> None:
        pause = alarm_pauses.build_pause(
            _payload(scope_type="rule", targets=[{"alarm_type": "alarm1", "rule_id": "phw-inactivity"}]),
            KNOWN_RULES,
            NOW,
        )
        assert pause["targets"] == [
            {"alarm_type": "alarm1", "rule_id": "phw-inactivity", "workflow_id": "phw-to-mpi"}
        ]

    def test_rule_scope_rejects_unknown_rule(self) -> None:
        with pytest.raises(PauseError, match="Unknown alarm rule"):
            alarm_pauses.build_pause(
                _payload(scope_type="rule", targets=[{"alarm_type": "alarm3", "rule_id": "phw-inactivity"}]),
                KNOWN_RULES,
                NOW,
            )

    @pytest.mark.parametrize(
        "target", [{"alarm_type": "alarm9", "rule_id": "x"}, {"alarm_type": "alarm1"}, "phw-inactivity"]
    )
    def test_rule_scope_rejects_malformed_targets(self, target: Any) -> None:
        with pytest.raises(PauseError, match="Invalid alarm rule target"):
            alarm_pauses.build_pause(_payload(scope_type="rule", targets=[target]), KNOWN_RULES, NOW)


class TestPersistence:
    def test_list_pauses_skips_documents_without_pause_id(self) -> None:
        with patch.object(alarm_pauses.cosmos_store, "query_documents", return_value=[_pause(), {"x": 1}]):
            assert [p["pause_id"] for p in alarm_pauses.list_pauses()] == ["p1"]

    def test_list_pauses_fails_open_when_cosmos_unavailable(self) -> None:
        # conftest disables Cosmos, so query_documents degrades to [] — no pause applies.
        assert alarm_pauses.list_pauses() == []

    def test_create_pause_requires_persistence(self) -> None:
        with pytest.raises(PausePersistenceError, match="not configured"):
            alarm_pauses.create_pause(_payload(), KNOWN_RULES, NOW)

    def test_create_pause_validates_before_checking_persistence(self) -> None:
        with pytest.raises(PauseError):
            alarm_pauses.create_pause(_payload(reason=""), KNOWN_RULES, NOW)

    def test_create_pause_persists_under_pause_id(self) -> None:
        with (
            patch.object(alarm_pauses.cosmos_store, "is_configured", return_value=True),
            patch.object(alarm_pauses.cosmos_store, "upsert_document", return_value=True) as mock_upsert,
            patch.object(alarm_pauses.cosmos_store, "query_documents", return_value=[]),
        ):
            view = alarm_pauses.create_pause(_payload(), KNOWN_RULES, NOW)
        pk, doc_id, document = mock_upsert.call_args[0]
        assert pk == "alarm-pause"
        assert doc_id == view["pause_id"] == document["pause_id"]
        assert mock_upsert.call_args.kwargs == {"doc_type": "alarm_pause"}
        assert view["status"] == "active"

    def test_create_pause_raises_when_write_fails(self) -> None:
        with (
            patch.object(alarm_pauses.cosmos_store, "is_configured", return_value=True),
            patch.object(alarm_pauses.cosmos_store, "upsert_document", return_value=False),
        ):
            with pytest.raises(PausePersistenceError, match="unavailable"):
                alarm_pauses.create_pause(_payload(), KNOWN_RULES, NOW)

    def test_purge_old_deletes_only_long_finished_pauses(self) -> None:
        pauses = [
            _pause("active"),
            _pause("recent", start=NOW - timedelta(days=5), end=NOW - timedelta(days=4)),
            _pause("old", start=NOW - timedelta(days=40), end=NOW - timedelta(days=31)),
            _pause("old-cancel", start=NOW - timedelta(days=35), cancelled=NOW - timedelta(days=36)),
        ]
        with patch.object(alarm_pauses.cosmos_store, "delete_document") as mock_delete:
            alarm_pauses.purge_old(pauses, NOW)
        assert sorted(c.args[1] for c in mock_delete.call_args_list) == ["old", "old-cancel"]


class TestCancelPause:
    def _cancel(self, stored: list[dict[str, Any]], pause_id: str = "p1") -> tuple[dict[str, Any], Any]:
        with (
            patch.object(alarm_pauses.cosmos_store, "is_configured", return_value=True),
            patch.object(alarm_pauses.cosmos_store, "query_documents", return_value=stored),
            patch.object(alarm_pauses.cosmos_store, "upsert_document", return_value=True) as mock_upsert,
        ):
            view = alarm_pauses.cancel_pause(pause_id, NOW)
        return view, mock_upsert

    def test_cancel_before_start_never_activates(self) -> None:
        view, mock_upsert = self._cancel([_pause(start=NOW + timedelta(hours=1))])
        saved = mock_upsert.call_args[0][2]
        assert saved["cancelled_at"] == NOW.isoformat()
        assert saved["end_at"] == (NOW + timedelta(hours=1)).isoformat()
        assert view["status"] == "cancelled"

    def test_cancel_after_start_ends_now(self) -> None:
        view, mock_upsert = self._cancel([_pause(end=None)])
        saved = mock_upsert.call_args[0][2]
        assert saved["end_at"] == NOW.isoformat()
        assert view["status"] == "ended"
        assert view["cancelled_early"] is True

    def test_cancel_unknown_pause_raises_not_found(self) -> None:
        with pytest.raises(PauseNotFoundError):
            self._cancel([], "missing")

    def test_cancel_already_ended_pause_is_rejected(self) -> None:
        with pytest.raises(PauseError, match="already ended"):
            self._cancel([_pause(end=NOW - timedelta(minutes=1))])

    def test_cancel_requires_persistence(self) -> None:
        with pytest.raises(PausePersistenceError):
            alarm_pauses.cancel_pause("p1", NOW)


class TestCancelRulePause:
    RULE_TARGET = [{"alarm_type": "alarm1", "rule_id": "phw-inactivity", "workflow_id": "phw-to-mpi"}]

    def test_single_rule_pause_is_cancelled(self) -> None:
        stored = [_pause("r1", scope_type="rule", targets=self.RULE_TARGET)]
        with (
            patch.object(alarm_pauses, "list_pauses", return_value=stored),
            patch.object(alarm_pauses, "cancel_pause") as mock_cancel,
        ):
            alarm_pauses.cancel_rule_pause("alarm1", "phw-inactivity", "phw-to-mpi", NOW)
        mock_cancel.assert_called_once_with("r1", NOW)

    def test_flow_pause_raises_conflict_with_pause_id(self) -> None:
        with patch.object(alarm_pauses, "list_pauses", return_value=[_pause("f1")]):
            with pytest.raises(PauseConflictError) as exc_info:
                alarm_pauses.cancel_rule_pause("alarm1", "phw-inactivity", "phw-to-mpi", NOW)
        assert exc_info.value.pause_id == "f1"

    def test_multi_rule_pause_raises_conflict(self) -> None:
        # Cancelling it would also resume the other rule.
        targets = [*self.RULE_TARGET, {"alarm_type": "alarm2", "rule_id": "phw-outgoing", "workflow_id": "phw-to-mpi"}]
        with patch.object(alarm_pauses, "list_pauses", return_value=[_pause("m1", scope_type="rule", targets=targets)]):
            with pytest.raises(PauseConflictError):
                alarm_pauses.cancel_rule_pause("alarm1", "phw-inactivity", "phw-to-mpi", NOW)

    def test_no_covering_pause_is_a_no_op(self) -> None:
        with (
            patch.object(alarm_pauses, "list_pauses", return_value=[]),
            patch.object(alarm_pauses, "cancel_pause") as mock_cancel,
        ):
            alarm_pauses.cancel_rule_pause("alarm1", "phw-inactivity", "phw-to-mpi", NOW)
        mock_cancel.assert_not_called()
