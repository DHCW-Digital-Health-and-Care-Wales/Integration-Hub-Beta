"""
Shared Cosmos DB config/state persistence and pause/unpause helpers for the
alarm services (alarm1.py, alarm2.py, alarm3.py).

Each alarm stores its rule config as a ``config`` document and per-rule alarm
state (last-fired timestamps, manual pauses) as a ``state`` document, both
within a Cosmos partition named after the alarm (``alarm1`` / ``alarm2`` /
``alarm3`` — see :mod:`dashboard.services.cosmos_store`). This module factors
out that previously triplicated persistence and pause/unpause logic; each
alarm module keeps its own thin, public wrapper functions (e.g.
``load_alarm_config``) so callers and tests are unaffected.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from dashboard.services import cosmos_store

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
    cosmos_store.upsert_document(partition_key, config_doc_id, cfg)


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
    cosmos_store.upsert_document(partition_key, state_doc_id, state)


def pause_rule(
    partition_key: str,
    rule_id: str,
    duration_minutes: int,
    reason: str,
    alarm_label: str,
    state_doc_id: str = "state",
) -> None:
    """Pause a specific alarm rule for ``duration_minutes``.

    Writes ``paused_until`` (ISO timestamp) and ``pause_reason`` into the rule's
    state entry. The alarm evaluator will skip the rule and return ``status='paused'``
    until that time has elapsed. ``alarm_label`` (e.g. ``"Alarm 1"``) is used only
    for the log message.
    """
    state = load_state(partition_key, state_doc_id)
    state_rules = state.setdefault("rules", {})
    now = datetime.now(timezone.utc)
    paused_until = now + timedelta(minutes=duration_minutes)
    state_rules.setdefault(rule_id, {}).update(
        {
            "paused_until": paused_until.isoformat(),
            "pause_reason": reason.strip(),
        }
    )
    save_state(partition_key, state, state_doc_id)
    log.info(
        "%s rule %s paused for %d minutes (until %s). Reason: %s",
        alarm_label,
        rule_id,
        duration_minutes,
        paused_until.isoformat(),
        reason or "(none)",
    )


def unpause_rule(
    partition_key: str,
    rule_id: str,
    alarm_label: str,
    state_doc_id: str = "state",
) -> None:
    """Remove a manual pause from a specific alarm rule, restoring normal evaluation."""
    state = load_state(partition_key, state_doc_id)
    state_rules = state.get("rules", {})
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
