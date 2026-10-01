"""Scheduled alarm pauses — one Cosmos document per pause in the ``alarm-pause`` partition.

A pause suppresses alarm evaluation (and therefore alert emails) for a scope of rules
between ``start_at`` and ``end_at`` (``None`` = until cancelled). Scopes:

  * ``rule``  – explicit ``{alarm_type, rule_id, workflow_id}`` targets
  * ``flows`` – every alarm type for the listed workflow ids, matched at evaluation time
    so rules added to a paused flow later are covered too
  * ``all``   – every rule of every alarm type

Pauses live in their own partition (not the alarm ``state`` documents) because the
evaluators rewrite the whole state document on every run, which would race with
user-initiated pause writes. Reads fail open: if Cosmos is unavailable no pause applies,
so alarms keep firing rather than being silently suppressed.

This module deliberately does not import the alarm modules (they import it), so rule
validation data is passed in by callers as ``known_rules``.
"""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from dashboard.services import cosmos_store

log = logging.getLogger(__name__)

PARTITION_KEY = "alarm-pause"
_DOC_TYPE = "alarm_pause"

LONDON_TZ = ZoneInfo("Europe/London")
ALARM_TYPES = ("alarm1", "alarm2", "alarm3")

SCOPE_RULE = "rule"
SCOPE_FLOWS = "flows"
SCOPE_ALL = "all"
SCOPES = (SCOPE_RULE, SCOPE_FLOWS, SCOPE_ALL)

STATUS_SCHEDULED = "scheduled"
STATUS_ACTIVE = "active"
STATUS_ENDED = "ended"
STATUS_CANCELLED = "cancelled"

END_DURATION = "duration"
END_UNTIL = "until"
END_INDEFINITE = "indefinite"

_WORKFLOW_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,119}$")
MAX_REASON_LENGTH = 200
MAX_REQUESTED_BY_LENGTH = 100
MAX_TARGETS = 500
MAX_DURATION_MINUTES = 365 * 24 * 60
# A start slightly in the past (form open for a minute, clock skew) is treated as "now".
_START_TOLERANCE = timedelta(minutes=2)
_MAX_LEAD_TIME = timedelta(days=365)
RECENT_WINDOW = timedelta(days=7)
_RETENTION = timedelta(days=30)
_DISPLAY_FMT = "%d %b %Y  %H:%M %Z"


class PauseError(ValueError):
    """Raised when a pause request fails validation."""

    def __init__(self, message: str):
        super().__init__(message)
        self.safe_message = message


class PauseNotFoundError(PauseError):
    """Raised when a pause id does not exist."""


class PauseConflictError(PauseError):
    """Raised when a single-rule resume is attempted on a rule covered by a broader pause."""

    def __init__(self, message: str, pause_id: str):
        super().__init__(message)
        self.pause_id = pause_id


class PausePersistenceError(RuntimeError):
    """Raised when a pause change could not be saved durably."""

    def __init__(self, message: str):
        super().__init__(message)
        self.safe_message = message


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    """Return the current time in UTC (wrapped so tests can patch a fixed clock)."""
    return datetime.now(timezone.utc)


def _parse_utc(raw: object) -> datetime | None:
    """Parse a stored ISO timestamp, normalising to UTC. Returns ``None`` for missing/invalid values."""
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def parse_london_datetime(raw: str, field_label: str) -> datetime:
    """Parse a ``datetime-local`` value entered as Europe/London time and return it in UTC.

    Rejects wall-clock times that don't exist (the spring-forward gap). Ambiguous
    autumn times resolve to the first occurrence (``fold=0``, BST).
    """
    try:
        naive = datetime.fromisoformat(str(raw).strip())
    except ValueError as exc:
        raise PauseError(f"{field_label} is not a valid date and time.") from exc
    if naive.tzinfo is not None:
        return naive.astimezone(timezone.utc)
    utc = naive.replace(tzinfo=LONDON_TZ, fold=0).astimezone(timezone.utc)
    if utc.astimezone(LONDON_TZ).replace(tzinfo=None) != naive:
        raise PauseError(f"{field_label} does not exist in UK time (clocks go forward).")
    return utc


def format_london(dt: datetime | None) -> str | None:
    """Format a UTC datetime for display in Europe/London time."""
    return dt.astimezone(LONDON_TZ).strftime(_DISPLAY_FMT) if dt else None


# ---------------------------------------------------------------------------
# Pure evaluation helpers
# ---------------------------------------------------------------------------


def pause_status(pause: Mapping[str, Any], now: datetime) -> str:
    """Return ``scheduled``, ``active``, ``ended`` or ``cancelled`` for a stored pause."""
    start = _parse_utc(pause.get("start_at"))
    end = _parse_utc(pause.get("end_at"))
    cancelled = _parse_utc(pause.get("cancelled_at"))
    if start is None:
        return STATUS_ENDED
    if cancelled is not None and cancelled <= start:
        return STATUS_CANCELLED
    if start > now:
        return STATUS_SCHEDULED
    if end is None or end > now:
        return STATUS_ACTIVE
    return STATUS_ENDED


def covers(pause: Mapping[str, Any], alarm_type: str, rule_id: str, workflow_id: str) -> bool:
    """Return whether ``pause`` applies to the given rule, regardless of time."""
    scope = pause.get("scope_type")
    if scope == SCOPE_ALL:
        return True
    targets = pause.get("targets") or []
    if scope == SCOPE_FLOWS:
        return bool(workflow_id) and workflow_id in targets
    if scope == SCOPE_RULE:
        return any(
            isinstance(t, Mapping) and t.get("alarm_type") == alarm_type and t.get("rule_id") == rule_id
            for t in targets
        )
    return False


def _end_sort_key(pause: Mapping[str, Any]) -> datetime:
    """Latest end first; indefinite pauses sort after every finite end."""
    return _parse_utc(pause.get("end_at")) or datetime.max.replace(tzinfo=timezone.utc)


def active_pause_for(
    pauses: Iterable[Mapping[str, Any]], alarm_type: str, rule_id: str, workflow_id: str, now: datetime
) -> Mapping[str, Any] | None:
    """Return the active pause covering a rule, preferring the one that ends last."""
    matching = [
        p for p in pauses if pause_status(p, now) == STATUS_ACTIVE and covers(p, alarm_type, rule_id, workflow_id)
    ]
    return max(matching, key=_end_sort_key) if matching else None


def next_scheduled_for(
    pauses: Iterable[Mapping[str, Any]], alarm_type: str, rule_id: str, workflow_id: str, now: datetime
) -> Mapping[str, Any] | None:
    """Return the soonest scheduled (not yet started) pause covering a rule."""
    matching = [
        p for p in pauses if pause_status(p, now) == STATUS_SCHEDULED and covers(p, alarm_type, rule_id, workflow_id)
    ]
    return min(matching, key=lambda p: _parse_utc(p.get("start_at")) or now) if matching else None


def pause_row_fields(pause: Mapping[str, Any], now: datetime) -> dict[str, Any]:
    """Return the alarm status-row fields describing an active pause."""
    end = _parse_utc(pause.get("end_at"))
    return {
        "pause_remaining": round((end - now).total_seconds() / 60, 0) if end else None,
        "pause_reason": pause.get("reason", ""),
        "paused_until": format_london(end),
        "pause_id": pause.get("pause_id"),
        "pause_scope": pause.get("scope_type"),
        "paused_by": pause.get("requested_by", ""),
        "pause_indefinite": end is None,
    }


def annotate_scheduled(rows: list[dict], alarm_type: str, pauses: list[dict], now: datetime) -> None:
    """Add a ``scheduled_pause`` summary (or ``None``) to each alarm status row in place."""
    for row in rows:
        upcoming = next_scheduled_for(
            pauses, alarm_type, row.get("id", ""), (row.get("workflow_id") or "").strip(), now
        )
        row["scheduled_pause"] = (
            {
                "pause_id": upcoming.get("pause_id"),
                "start_display": format_london(_parse_utc(upcoming.get("start_at"))),
            }
            if upcoming
            else None
        )


def summarise(pauses: Iterable[Mapping[str, Any]], now: datetime) -> dict[str, int]:
    """Count active and scheduled pauses (for the overview indicators)."""
    statuses = [pause_status(p, now) for p in pauses]
    return {
        "active": statuses.count(STATUS_ACTIVE),
        "scheduled": statuses.count(STATUS_SCHEDULED),
    }


def current_summary() -> dict[str, int]:
    """Return active/scheduled pause counts as of now."""
    return summarise(list_pauses(), _utcnow())


def current_flow_summary(workflow_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    """Return :func:`flow_pause_summary` as of now."""
    return flow_pause_summary(list_pauses(), workflow_ids, _utcnow())


def _touches_flow(pause: Mapping[str, Any], workflow_id: str) -> bool:
    """Whether a pause affects any alarm of ``workflow_id`` (rule-scope via stored target workflow ids)."""
    scope = pause.get("scope_type")
    if scope == SCOPE_ALL:
        return True
    targets = pause.get("targets") or []
    if scope == SCOPE_FLOWS:
        return workflow_id in targets
    return any(isinstance(t, Mapping) and t.get("workflow_id") == workflow_id for t in targets)


def flow_pause_summary(
    pauses: list[dict], workflow_ids: Iterable[str], now: datetime
) -> dict[str, dict[str, Any]]:
    """Return ``{workflow_id: {"active": view|None, "scheduled": view|None}}`` for flow-level badges."""
    live = [(p, pause_status(p, now)) for p in pauses]
    result: dict[str, dict[str, Any]] = {}
    for wid in workflow_ids:
        active = [p for p, s in live if s == STATUS_ACTIVE and _touches_flow(p, wid)]
        scheduled = [p for p, s in live if s == STATUS_SCHEDULED and _touches_flow(p, wid)]
        if not active and not scheduled:
            continue
        result[wid] = {
            "active": to_view(max(active, key=_end_sort_key), now) if active else None,
            "scheduled": (
                to_view(min(scheduled, key=lambda p: _parse_utc(p.get("start_at")) or now), now)
                if scheduled
                else None
            ),
        }
    return result


def to_view(pause: Mapping[str, Any], now: datetime) -> dict[str, Any]:
    """Return a template/JSON-friendly representation of a stored pause."""
    start = _parse_utc(pause.get("start_at"))
    end = _parse_utc(pause.get("end_at"))
    cancelled = _parse_utc(pause.get("cancelled_at"))
    status = pause_status(pause, now)
    return {
        "pause_id": pause.get("pause_id"),
        "scope_type": pause.get("scope_type"),
        "targets": list(pause.get("targets") or []),
        "start_at": pause.get("start_at"),
        "end_at": pause.get("end_at"),
        "start_display": format_london(start),
        "end_display": format_london(end),
        "indefinite": end is None,
        "reason": pause.get("reason", ""),
        "requested_by": pause.get("requested_by", ""),
        "created_display": format_london(_parse_utc(pause.get("created_at"))),
        "cancelled_display": format_london(cancelled),
        "cancelled_early": cancelled is not None and status == STATUS_ENDED,
        "status": status,
        "remaining_minutes": (
            round((end - now).total_seconds() / 60, 0) if end and status == STATUS_ACTIVE else None
        ),
    }


def group_for_display(pauses: list[dict], now: datetime) -> dict[str, list[dict[str, Any]]]:
    """Split pauses into active / scheduled / recently-ended lists for the pauses page."""
    views = [to_view(p, now) for p in pauses]
    active = sorted((v for v in views if v["status"] == STATUS_ACTIVE), key=lambda v: v["start_at"] or "")
    scheduled = sorted((v for v in views if v["status"] == STATUS_SCHEDULED), key=lambda v: v["start_at"] or "")
    recent_cutoff = now - RECENT_WINDOW
    recent = [
        v
        for v in views
        if v["status"] in (STATUS_ENDED, STATUS_CANCELLED) and (_finished_at(v) or now) >= recent_cutoff
    ]
    recent.sort(key=lambda v: _finished_at(v) or now, reverse=True)
    return {"active": active, "scheduled": scheduled, "recent": recent}


def _finished_at(pause: Mapping[str, Any]) -> datetime | None:
    """When a pause stopped applying: its cancellation time, else its end time."""
    return _parse_utc(pause.get("cancelled_at")) or _parse_utc(pause.get("end_at"))


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_text(value: Any, field_label: str, max_length: int) -> str:
    """Return ``value`` stripped, raising ``PauseError`` if it is missing, blank or too long."""
    if not isinstance(value, str) or not value.strip():
        raise PauseError(f"{field_label} is required.")
    value = value.strip()
    if len(value) > max_length:
        raise PauseError(f"{field_label} is too long (max {max_length} characters).")
    return value


def _validate_targets(
    scope_type: str, targets: Any, known_rules: Mapping[str, Mapping[str, str]]
) -> list[Any]:
    """Validate scope targets. ``known_rules`` maps alarm_type -> {rule_id: workflow_id}.

    Returns ``[]`` for ``all`` scope, a de-duplicated list of workflow ids for ``flows``,
    or a de-duplicated list of ``{alarm_type, rule_id, workflow_id}`` for ``rule`` scope.
    The rule's workflow id is stored so the Flows page can badge the affected flow.
    """
    if scope_type == SCOPE_ALL:
        return []
    if not isinstance(targets, list) or not targets:
        raise PauseError("Select at least one flow or alarm to pause.")
    if len(targets) > MAX_TARGETS:
        raise PauseError(f"Too many targets (max {MAX_TARGETS}).")

    if scope_type == SCOPE_FLOWS:
        workflow_ids: list[str] = []
        for wid in targets:
            if not isinstance(wid, str) or not _WORKFLOW_ID_RE.match(wid.strip()):
                raise PauseError("Invalid flow id.")
            if wid.strip() not in workflow_ids:
                workflow_ids.append(wid.strip())
        return workflow_ids

    rule_targets: list[dict[str, str]] = []
    for target in targets:
        if not isinstance(target, Mapping):
            raise PauseError("Invalid alarm rule target.")
        alarm_type = target.get("alarm_type")
        rule_id = target.get("rule_id")
        if alarm_type not in ALARM_TYPES or not isinstance(rule_id, str):
            raise PauseError("Invalid alarm rule target.")
        rules = known_rules.get(alarm_type, {})
        if rule_id not in rules:
            raise PauseError(f"Unknown alarm rule: {rule_id}")
        entry = {"alarm_type": alarm_type, "rule_id": rule_id, "workflow_id": rules[rule_id]}
        if entry not in rule_targets:
            rule_targets.append(entry)
    return rule_targets


def _resolve_start(raw_start: Any, now: datetime) -> datetime:
    """Return the UTC start time: ``now`` for an empty/"now" value, else a validated UK-time input."""
    if raw_start in (None, "", "now"):
        return now
    start = parse_london_datetime(raw_start, "Start time")
    if start < now - _START_TOLERANCE:
        raise PauseError("Start time is in the past.")
    if start > now + _MAX_LEAD_TIME:
        raise PauseError("Start time must be within the next 365 days.")
    return max(start, now)


def _resolve_end(payload: Mapping[str, Any], start: datetime) -> datetime | None:
    """Return the UTC end time for ``end_mode`` (``duration`` / ``until``), or ``None`` for ``indefinite``."""
    end_mode = payload.get("end_mode", END_DURATION)
    if end_mode == END_INDEFINITE:
        return None
    if end_mode == END_UNTIL:
        end = parse_london_datetime(payload.get("end", ""), "End time")
        if end <= start:
            raise PauseError("End time must be after the start time.")
        return end
    if end_mode == END_DURATION:
        try:
            minutes = int(payload.get("duration_minutes", 0))
        except (TypeError, ValueError) as exc:
            raise PauseError("Duration must be a whole number of minutes.") from exc
        if minutes < 1 or minutes > MAX_DURATION_MINUTES:
            raise PauseError("Duration must be between 1 minute and 365 days.")
        return start + timedelta(minutes=minutes)
    raise PauseError("Invalid end option.")


def build_pause(
    payload: Mapping[str, Any], known_rules: Mapping[str, Mapping[str, str]], now: datetime
) -> dict[str, Any]:
    """Validate a create-pause request and return the document to store (without persisting)."""
    scope_type = payload.get("scope_type")
    if scope_type not in SCOPES:
        raise PauseError("Invalid pause scope.")
    targets = _validate_targets(scope_type, payload.get("targets"), known_rules)
    reason = _validate_text(payload.get("reason"), "Reason", MAX_REASON_LENGTH)
    requested_by = _validate_text(payload.get("requested_by"), "Requested by", MAX_REQUESTED_BY_LENGTH)
    start = _resolve_start(payload.get("start"), now)
    end = _resolve_end(payload, start)
    return {
        "pause_id": str(uuid.uuid4()),
        "scope_type": scope_type,
        "targets": targets,
        "start_at": start.isoformat(),
        "end_at": end.isoformat() if end else None,
        "reason": reason,
        "requested_by": requested_by,
        "created_at": now.isoformat(),
        "cancelled_at": None,
    }


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def _ensure_persistence_configured() -> None:
    """Refuse writes when there is nowhere durable to store them — a lost pause would page on-call."""
    if not cosmos_store.is_configured():
        raise PausePersistenceError("Pause persistence is not configured.")


def _persist(pause: dict[str, Any]) -> None:
    """Upsert a pause document, raising ``PausePersistenceError`` if the write fails."""
    # The id is stored as "pause_id" because cosmos_store strips "id" on read.
    if not cosmos_store.upsert_document(PARTITION_KEY, pause["pause_id"], pause, doc_type=_DOC_TYPE):
        raise PausePersistenceError("Pause persistence is currently unavailable.")


def list_pauses(strict: bool = False) -> list[dict]:
    """Return every stored pause.

    Fails open (``[]``) when Cosmos is unavailable, unless ``strict`` — then raises
    ``PausePersistenceError`` so write paths never act on a failed read.
    """
    try:
        documents = cosmos_store.query_documents(PARTITION_KEY, strict=strict)
    except cosmos_store.CosmosUnavailableError as exc:
        raise PausePersistenceError("Pause persistence is currently unavailable.") from exc
    return [p for p in documents if p.get("pause_id")]


def purge_old(pauses: list[dict], now: datetime) -> None:
    """Delete ended/cancelled pauses that finished more than the retention period ago."""
    cutoff = now - _RETENTION
    for pause in pauses:
        if pause_status(pause, now) not in (STATUS_ENDED, STATUS_CANCELLED):
            continue
        finished = _finished_at(pause)
        if finished is not None and finished < cutoff:
            cosmos_store.delete_document(PARTITION_KEY, pause["pause_id"])


def create_pause(
    payload: Mapping[str, Any],
    known_rules: Mapping[str, Mapping[str, str]],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Validate and persist a new pause, returning its view."""
    now = now or _utcnow()
    pause = build_pause(payload, known_rules, now)
    _ensure_persistence_configured()
    _persist(pause)
    log.info(
        "Alarm pause %s created by %s: scope=%s targets=%s start=%s end=%s reason=%s",
        pause["pause_id"],
        pause["requested_by"],
        pause["scope_type"],
        pause["targets"],
        pause["start_at"],
        pause["end_at"] or "indefinite",
        pause["reason"],
    )
    purge_old(list_pauses(), now)
    return to_view(pause, now)


def cancel_pause(pause_id: str, now: datetime | None = None) -> dict[str, Any]:
    """Cancel a scheduled pause, or end an active one immediately. Returns the updated view."""
    now = now or _utcnow()
    _ensure_persistence_configured()
    pauses = list_pauses(strict=True)
    pause = next((p for p in pauses if p.get("pause_id") == pause_id), None)
    if pause is None:
        raise PauseNotFoundError("Pause not found.")
    status = pause_status(pause, now)
    if status == STATUS_SCHEDULED:
        pause["cancelled_at"] = now.isoformat()
    elif status == STATUS_ACTIVE:
        pause["cancelled_at"] = now.isoformat()
        pause["end_at"] = now.isoformat()
    else:
        raise PauseError("This pause has already ended.")
    _persist(pause)
    log.info("Alarm pause %s cancelled (was %s)", pause_id, status)
    purge_old(pauses, now)
    return to_view(pause, now)


def cancel_rule_pause(alarm_type: str, rule_id: str, workflow_id: str, now: datetime | None = None) -> None:
    """Resume a single rule by cancelling the active single-rule pause covering it.

    Raises :class:`PauseConflictError` when the covering pause spans more than this rule
    (flow/all scope or several rules) — cancelling it would resume other alarms too.
    Raises :class:`PausePersistenceError` when pauses cannot be read.
    A no-op when no pause record covers the rule.
    """
    now = now or _utcnow()
    pause = active_pause_for(list_pauses(strict=True), alarm_type, rule_id, workflow_id, now)
    if pause is None:
        return
    if pause.get("scope_type") != SCOPE_RULE or len(pause.get("targets") or []) != 1:
        raise PauseConflictError(
            "This alarm is paused as part of a wider pause. Manage it from the Alarm Pauses page.",
            str(pause.get("pause_id")),
        )
    cancel_pause(str(pause["pause_id"]), now)
