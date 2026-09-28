"""Seed the local Cosmos DB emulator with example alarm rules (and optionally example pauses).

Development tool only — lives outside the ``dashboard`` package so it is not copied into the
container image, and refuses to run against anything other than a local emulator endpoint.

Creates Alarm 1 (Inactivity), Alarm 2 (Outgoing Volume) and Alarm 3 (Failures) rules for every
flow in ``demo_data.DEMO_FLOWS`` (the real flow ids plus the fictional stress-test ones), with a
deterministic mix of enabled/disabled rules, thresholds and email settings so the alarm pages,
Alarms by Flow and the Flows page all have varied data. Every seeded rule is tagged
``"example": True`` so it can be removed again without touching hand-made rules.

With ``--with-pauses`` it also adds pauses covering each pause state (active, scheduled,
indefinite, all-flows, ended early, cancelled), tagged via ``requested_by``.

Usage (from ``dashboard/``, with the emulator running and ``COSMOS_ENDPOINT`` set in ``.env``)::

    uv run python scripts/seed_example_alarms.py                 # add missing example rules
    uv run python scripts/seed_example_alarms.py --with-pauses   # ...plus example pauses
    uv run python scripts/seed_example_alarms.py --overwrite     # reset example rules to defaults
    uv run python scripts/seed_example_alarms.py --remove        # delete all example rules/pauses
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

from dashboard import config
from dashboard.services import alarm1, alarm2, alarm3, alarm_base, alarm_pauses, cosmos_store
from dashboard.services.demo_data import DEMO_FLOWS

log = logging.getLogger("seed_example_alarms")

EXAMPLE_TAG = "example"
EXAMPLE_REQUESTED_BY = "Example data (seed script)"
_LOCAL_HOSTS = ("localhost", "127.0.0.1", "cosmos-emulator")

# Alarm type -> (Cosmos partition, rule-id suffix); suffixes match each module's generate_rule_id().
_ALARMS: dict[str, tuple[str, str]] = {
    "alarm1": (alarm1.COSMOS_PK, "inactivity"),
    "alarm2": (alarm2.COSMOS_PK, "outgoing"),
    "alarm3": (alarm3.COSMOS_PK, "failures"),
}

# Threshold presets (day, evening, weekend minutes) cycled across flows for variety.
_INACTIVITY_PRESETS = [(30, 60, 120), (60, 120, 240), (15, 45, 90), (120, 240, 480)]
_FAILURE_PRESETS = [(15, 1), (30, 5), (60, 10), (5, 1)]  # (window minutes, failure threshold)


def ensure_local_endpoint(endpoint: str) -> None:
    """Exit unless ``endpoint`` points at a local emulator — never seed shared/cloud Cosmos accounts."""
    if not endpoint:
        sys.exit("COSMOS_ENDPOINT is not set — start the emulator and configure dashboard/.env first.")
    if not any(host in endpoint.lower() for host in _LOCAL_HOSTS):
        sys.exit(f"Refusing to seed non-local Cosmos endpoint: {endpoint}")


def _label(flow_id: str) -> str:
    return DEMO_FLOWS.get(flow_id, {}).get("label") or flow_id


def build_example_rules(flow_ids: list[str]) -> dict[str, dict[str, dict[str, Any]]]:
    """Return ``{alarm_type: {rule_id: rule_config}}`` example rules for each flow.

    Variety is derived from the flow's position so repeated runs produce identical data:
    roughly one in five rules is disabled and every third enabled rule has email alerts on.
    """
    rules: dict[str, dict[str, dict[str, Any]]] = {alarm_type: {} for alarm_type in _ALARMS}
    for i, wid in enumerate(flow_ids):
        day, evening, weekend = _INACTIVITY_PRESETS[i % len(_INACTIVITY_PRESETS)]
        window, failures = _FAILURE_PRESETS[i % len(_FAILURE_PRESETS)]
        common = {
            "workflow_id": wid,
            "alerting_gap_minutes": 30 if i % 2 else 60,
            "email_ooh_enabled": False,
            EXAMPLE_TAG: True,
        }
        for offset, alarm_type in enumerate(_ALARMS):
            enabled = (i + offset) % 5 != 4
            email = enabled and (i + offset) % 3 == 0
            suffix = _ALARMS[alarm_type][1]
            rule: dict[str, Any] = {
                **common,
                "display_name": f"{_label(wid)} {suffix.title()}",
                "alarm_enabled": enabled,
                "email_alerts_enabled": email,
            }
            if alarm_type == "alarm3":
                rule.update(window_duration_minutes=window, threshold=failures)
            else:
                # Alarm 2 watches outbound traffic, which is naturally quieter, so allow longer gaps.
                factor = 2 if alarm_type == "alarm2" else 1
                rule.update(
                    day_threshold_minutes=day * factor,
                    evening_threshold_minutes=evening * factor,
                    weekend_threshold_minutes=weekend * factor,
                )
            rules[alarm_type][f"{wid}-{suffix}"] = rule
    return rules


def merge_rules(existing: dict[str, Any], examples: dict[str, dict[str, Any]], overwrite: bool) -> tuple[int, int]:
    """Merge example rules into an alarm config document in place. Returns ``(added, skipped)``.

    Existing rules are never touched unless ``overwrite`` is set *and* the rule is itself an
    example rule — hand-made rules with a colliding id are always left alone.
    """
    stored = existing.setdefault("rules", {})
    added = skipped = 0
    for rule_id, rule in examples.items():
        current = stored.get(rule_id)
        if current is None or (overwrite and current.get(EXAMPLE_TAG)):
            stored[rule_id] = dict(rule)
            added += 1
        else:
            skipped += 1
    return added, skipped


def remove_example_rules(existing: dict[str, Any]) -> int:
    """Delete every example-tagged rule from an alarm config document in place. Returns the count removed."""
    stored = existing.setdefault("rules", {})
    example_ids = [rid for rid, rule in stored.items() if rule.get(EXAMPLE_TAG)]
    for rid in example_ids:
        del stored[rid]
    return len(example_ids)


def build_example_pauses(
    known_rules: dict[str, dict[str, str]], flow_ids: list[str], now: datetime
) -> list[dict[str, Any]]:
    """Return example pause documents covering each pause status.

    Active/scheduled pauses go through ``alarm_pauses.build_pause`` so they are validated exactly
    like user-created ones; ended/cancelled ones are backdated by adjusting the built document.
    """
    first_rule = next(iter(known_rules["alarm1"]))

    def build(offset_start: timedelta | None, **payload: Any) -> dict[str, Any]:
        base = {"reason": payload.pop("reason"), "requested_by": EXAMPLE_REQUESTED_BY, **payload}
        pause = alarm_pauses.build_pause(base, known_rules, now)
        if offset_start is not None:
            # Backdate after validation (build_pause rejects past starts by design).
            duration = datetime.fromisoformat(pause["end_at"]) - datetime.fromisoformat(pause["start_at"])
            start = now + offset_start
            pause.update(start_at=start.isoformat(), end_at=(start + duration).isoformat(),
                         created_at=(start - timedelta(hours=1)).isoformat())
        return pause

    in_two_days = (now + timedelta(days=2)).astimezone(alarm_pauses.LONDON_TZ).replace(hour=22, minute=0)
    next_week = (now + timedelta(days=7)).astimezone(alarm_pauses.LONDON_TZ).replace(hour=6, minute=0)
    fmt = "%Y-%m-%dT%H:%M"

    pauses = [
        build(None, scope_type="flows", targets=[flow_ids[0]], end_mode="duration", duration_minutes=90,
              reason="Server patching"),
        build(None, scope_type="rule", targets=[{"alarm_type": "alarm1", "rule_id": first_rule}],
              end_mode="duration", duration_minutes=45, reason="Known upstream outage"),
        build(None, scope_type="flows", targets=[flow_ids[-1]], end_mode="indefinite",
              reason="System being decommissioned"),
        build(None, scope_type="flows", targets=flow_ids[1:4], start=in_two_days.strftime(fmt),
              end_mode="duration", duration_minutes=240, reason="Planned network maintenance window"),
        build(None, scope_type="all", targets=[], start=next_week.strftime(fmt), end_mode="until",
              end=(next_week + timedelta(hours=2)).strftime(fmt), reason="Integration Hub platform upgrade"),
        build(-timedelta(days=2), scope_type="flows", targets=flow_ids[4:6], end_mode="duration",
              duration_minutes=120, reason="Deployment of new transformer"),
    ]
    # Ended early: started yesterday, cancelled half-way through.
    ended_early = build(-timedelta(days=1), scope_type="flows", targets=[flow_ids[2]], end_mode="duration",
                        duration_minutes=180, reason="Database failover test")
    cancelled_at = datetime.fromisoformat(ended_early["start_at"]) + timedelta(minutes=90)
    ended_early.update(end_at=cancelled_at.isoformat(), cancelled_at=cancelled_at.isoformat())
    # Cancelled before it started.
    cancelled = build(-timedelta(days=3), scope_type="all", targets=[], end_mode="duration", duration_minutes=60,
                      reason="Rescheduled maintenance")
    cancelled["cancelled_at"] = (datetime.fromisoformat(cancelled["start_at"]) - timedelta(hours=4)).isoformat()
    return [*pauses, ended_early, cancelled]


def _is_example_pause(pause: dict[str, Any]) -> bool:
    return pause.get("requested_by") == EXAMPLE_REQUESTED_BY


def _save_pause(pause: dict[str, Any]) -> None:
    if not cosmos_store.upsert_document(alarm_pauses.PARTITION_KEY, pause["pause_id"], pause, doc_type="alarm_pause"):
        sys.exit("Failed to write pause to Cosmos — is the emulator running?")


def seed(with_pauses: bool, overwrite: bool) -> None:
    """Add example rules (and optionally pauses), leaving non-example data untouched."""
    flow_ids = list(DEMO_FLOWS)
    examples = build_example_rules(flow_ids)
    for alarm_type, (pk, _suffix) in _ALARMS.items():
        cfg = alarm_base.load_config(pk)
        added, skipped = merge_rules(cfg, examples[alarm_type], overwrite)
        alarm_base.save_config(pk, cfg)
        log.info("%s: added %d example rules (%d already present)", alarm_type, added, skipped)

    if not with_pauses:
        return
    existing = [p for p in alarm_pauses.list_pauses() if _is_example_pause(p)]
    if existing and not overwrite:
        log.info("pauses: %d example pauses already present — use --overwrite to replace them", len(existing))
        return
    for pause in existing:
        cosmos_store.delete_document(alarm_pauses.PARTITION_KEY, pause["pause_id"])
    known_rules = {alarm_type: {rid: r["workflow_id"] for rid, r in examples[alarm_type].items()}
                   for alarm_type in _ALARMS}
    pauses = build_example_pauses(known_rules, flow_ids, datetime.now(timezone.utc))
    for pause in pauses:
        _save_pause(pause)
    log.info("pauses: added %d example pauses", len(pauses))


def remove() -> None:
    """Delete every example-tagged rule and example pause."""
    for alarm_type, (pk, _suffix) in _ALARMS.items():
        cfg = alarm_base.load_config(pk)
        removed = remove_example_rules(cfg)
        alarm_base.save_config(pk, cfg)
        log.info("%s: removed %d example rules", alarm_type, removed)
    example_pauses = [p for p in alarm_pauses.list_pauses() if _is_example_pause(p)]
    for pause in example_pauses:
        cosmos_store.delete_document(alarm_pauses.PARTITION_KEY, pause["pause_id"])
    log.info("pauses: removed %d example pauses", len(example_pauses))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--remove", action="store_true", help="delete all example rules and pauses")
    group.add_argument("--with-pauses", action="store_true", help="also add example pauses")
    parser.add_argument("--overwrite", action="store_true", help="reset existing example rules/pauses")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    # The Azure SDK logs every HTTP request/response at INFO.
    logging.getLogger("azure").setLevel(logging.WARNING)
    ensure_local_endpoint(config.COSMOS_ENDPOINT)
    if args.remove:
        remove()
    else:
        seed(with_pauses=args.with_pauses, overwrite=args.overwrite)


if __name__ == "__main__":
    main()
