"""
Shared Cosmos DB config/state persistence and pause helpers for the alarm services
(alarm1.py, alarm2.py, alarm3.py).

Each alarm stores its rule config as a ``config`` document and per-rule alarm
state (last-fired timestamps) as a ``state`` document, both within a Cosmos
partition named after the alarm (``alarm1`` / ``alarm2`` / ``alarm3`` — see
:mod:`dashboard.services.cosmos_store`). This module factors out that previously
triplicated persistence logic; each alarm module keeps its own thin, public wrapper
functions (e.g. ``load_alarm_config``) so callers and tests are unaffected.

Pauses are stored as separate records by :mod:`dashboard.services.alarm_pauses`.
The helpers here adapt those records to the evaluators: :func:`resolve_pause` decides
whether a rule is paused right now, and :func:`pause_rule_now` / :func:`resume_rule`
back the single-rule Pause/Resume buttons. The older ``paused_until`` field in the
state document is no longer written, but is still honoured until it expires so pauses
created before the upgrade keep working.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from dashboard.services import alarm_pauses, cosmos_store

log = logging.getLogger(__name__)


def load_config(partition_key: str, config_doc_id: str = "config") -> dict:
    """Load an alarm's rule config from Cosmos DB. Returns empty config when none is stored."""
    doc = cosmos_store.get_document(partition_key, config_doc_id)
    if not doc:
        return {"rules": {}}
    doc.setdefault("rules", {})
    return doc


def save_config(partition_key: str, cfg: dict, config_doc_id: str = "config") -> None:
    """Persist an alarm's rule config to Cosmos DB."""
    cosmos_store.upsert_document(partition_key, config_doc_id, cfg, doc_type="alarm_config")


def load_state(partition_key: str, state_doc_id: str = "state") -> dict:
    """Load an alarm's per-rule state (last_alarm_at timestamps, pauses) from Cosmos.

    Returns empty state when none is stored.
    """
    doc = cosmos_store.get_document(partition_key, state_doc_id)
    if not doc:
        return {"rules": {}}
    doc.setdefault("rules", {})
    return doc


def save_state(partition_key: str, state: dict, state_doc_id: str = "state") -> None:
    """Persist an alarm's per-rule state to Cosmos DB."""
    cosmos_store.upsert_document(partition_key, state_doc_id, state, doc_type="alarm_state")


# Pause fields present on every status row; overwritten by resolve_pause() output when paused.
EMPTY_PAUSE_FIELDS: dict = {
    "pause_remaining": None,
    "pause_reason": "",
    "paused_until": None,
    "pause_id": None,
    "pause_scope": None,
    "paused_by": "",
    "pause_indefinite": False,
}


def pause_rule_now(
    alarm_type: str,
    known_rules: dict[str, str],
    rule_id: str,
    duration_minutes: int | None,
    reason: str,
    requested_by: str,
) -> dict:
    """Create a single-rule pause starting now; ``duration_minutes=None`` pauses until cancelled.

    ``known_rules`` maps this alarm type's rule ids to workflow ids. Raises
    ``alarm_pauses.PauseError`` / ``PausePersistenceError`` on invalid input or storage failure.
    """
    payload = {
        "scope_type": alarm_pauses.SCOPE_RULE,
        "targets": [{"alarm_type": alarm_type, "rule_id": rule_id}],
        "start": None,
        "end_mode": alarm_pauses.END_INDEFINITE if duration_minutes is None else alarm_pauses.END_DURATION,
        "duration_minutes": duration_minutes,
        "reason": reason,
        "requested_by": requested_by,
    }
    return alarm_pauses.create_pause(payload, {alarm_type: known_rules})


def resume_rule(
    alarm_type: str,
    known_rules: dict[str, str],
    rule_id: str,
    alarm_label: str,
    state_doc_id: str = "state",
) -> None:
    """Resume a rule: cancel its single-rule pause record, then clear any legacy pause.

    Raises ``alarm_pauses.PauseConflictError`` if the rule is covered by a wider pause,
    leaving the legacy pause untouched.
    """
    alarm_pauses.cancel_rule_pause(alarm_type, rule_id, known_rules.get(rule_id, ""))
    unpause_rule(alarm_type, rule_id, alarm_label, state_doc_id)


def resolve_pause(
    rule_state: dict,
    alarm_type: str,
    rule_id: str,
    workflow_id: str,
    pauses: list[dict],
    now: datetime,
) -> dict | None:
    """Return status-row pause fields if the rule is paused now, else ``None``.

    Checks pause records first, then the legacy per-rule ``paused_until`` state field
    (no longer written, honoured until it expires).
    """
    pause = alarm_pauses.active_pause_for(pauses, alarm_type, rule_id, workflow_id, now)
    if pause is not None:
        return alarm_pauses.pause_row_fields(pause, now)

    legacy_until = parse_log_analytics_datetime(rule_state.get("paused_until"))
    if legacy_until and legacy_until > now:
        return {
            "pause_remaining": round((legacy_until - now).total_seconds() / 60, 0),
            "pause_reason": rule_state.get("pause_reason", ""),
            "paused_until": alarm_pauses.format_london(legacy_until),
            "pause_id": None,
            "pause_scope": alarm_pauses.SCOPE_RULE,
            "paused_by": "",
            "pause_indefinite": False,
        }
    return None


def clear_expired_legacy_pause(state_rules: dict, rule_id: str, now: datetime) -> bool:
    """Drop an elapsed legacy ``paused_until`` from ``state_rules`` in place. Returns whether it changed."""
    rule_state = state_rules.get(rule_id, {})
    legacy_until = parse_log_analytics_datetime(rule_state.get("paused_until"))
    if not legacy_until or legacy_until > now:
        return False
    rule_state.pop("paused_until", None)
    rule_state.pop("pause_reason", None)
    if not rule_state:
        del state_rules[rule_id]
    return True


def unpause_rule(
    partition_key: str,
    rule_id: str,
    alarm_label: str,
    state_doc_id: str = "state",
) -> None:
    """Remove a legacy ``paused_until`` pause from a rule's state, restoring normal evaluation."""
    state = load_state(partition_key, state_doc_id)
    state_rules = state.get("rules", {})
    if "paused_until" not in state_rules.get(rule_id, {}):
        return
    rule_state = state_rules.get(rule_id, {})
    rule_state.pop("paused_until", None)
    rule_state.pop("pause_reason", None)
    if rule_state:
        state_rules[rule_id] = rule_state
    elif rule_id in state_rules:
        del state_rules[rule_id]
    save_state(partition_key, state, state_doc_id)
    log.info("%s rule %s unpaused", alarm_label, rule_id)


def parse_log_analytics_datetime(raw: object) -> datetime | None:
    """Parse a datetime from a Log Analytics row value or ISO string, normalising to UTC."""
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(raw))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def format_duration(minutes: float) -> str:
    """Format a duration in minutes as a human-readable string (e.g. ``"2.5 hours"``)."""
    if minutes < 1:
        return "< 1 minute"
    if minutes < 60:
        m = int(minutes)
        return f"{m} minute{'s' if m != 1 else ''}"
    hours = minutes / 60
    if hours < 24:
        return f"{hours:.1f} hour{'s' if hours != 1.0 else ''}"
    days = hours / 24
    return f"{days:.1f} day{'s' if days != 1.0 else ''}"
