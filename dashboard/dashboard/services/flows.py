"""
Flow definitions and health calculation for the Integration Hub.
Each flow represents an end-to-end HL7 message path.

Primary discovery: Container App environment variables via ``arm.discover_flows()``.
Fallback: static ``_FLOW_DEFS`` with suffix-based queue matching (used when the
Container Apps API is unavailable or not configured).
"""

from __future__ import annotations

import logging

from dashboard import config
from dashboard.services.arm import (  # noqa: PLC0415 (deferred to avoid circular at load time)
    discover_flows,
    get_subscription_consumers_by_topic,
)
from dashboard.services.service_bus import (  # noqa: PLC0415
    get_queue_names,
    get_subscriptions,
    get_topic_names,
    resolve_by_suffix,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Static fallback flow definitions
#
# Used only when Container App discovery is unavailable (e.g. local dev
# without Azure credentials).  Queue names are resolved by suffix matching
# against the Service Bus namespace using the Terraform naming convention:
#   queues:        lower("${prefix}-SBQ-{Part}")
#   topics:        lower("${prefix}-SBT-{Part}")
#   subscriptions: lower("${prefix}-SBS-{Part}")
# ---------------------------------------------------------------------------

_FLOW_DEFS: list[dict] = [
    {
        "id": "phw-to-mpi",
        "label": "PHW → MPI",
        "source": "PHW",
        "source_port": 2575,
        "pre_queue_suffix": "sbq-phw-hl7-transformer",
        "post_queue_suffix": "sbq-hl7-sender",
        "transformer": "PHW Transformer",
        "destination": "MPI",
        "colour": "#3b82f6",
        "icon": "bi-heart-pulse",
    },
    {
        "id": "paris-to-mpi",
        "label": "Paris → MPI",
        "source": "Paris",
        "source_port": 2577,
        "pre_queue_suffix": None,
        "post_queue_suffix": None,
        "transformer": None,
        "destination": "MPI",
        "colour": "#a855f7",
        "icon": "bi-activity",
    },
    {
        "id": "mosaiq-to-mpi",
        "label": "Mosaiq → MPI",
        "source": "Mosaiq",
        "source_port": 2583,
        "pre_queue_suffix": None,
        "post_queue_suffix": None,
        "transformer": None,
        "destination": "MPI",
        "colour": "#ec4899",
        "icon": "bi-radioactive",
    },
    {
        "id": "chemocare-to-mpi",
        "label": "ChemoCare → MPI",
        "source": "ChemoCare",
        "source_port": 2578,
        "pre_queue_suffix": "sbq-chemo-hl7-transformer",
        "post_queue_suffix": "sbq-chemo-hl7-sender",
        "transformer": "Chemo Transformer",
        "destination": "MPI",
        "colour": "#06b6d4",
        "icon": "bi-capsule",
    },
    {
        "id": "pims-to-mpi",
        "label": "PIMS → MPI",
        "source": "PIMS",
        "source_port": 2579,
        "pre_queue_suffix": "sbq-pims-hl7-transformer",
        "post_queue_suffix": "sbq-pims-hl7-sender",
        "transformer": "PIMS Transformer",
        "destination": "MPI",
        "colour": "#22c55e",
        "icon": "bi-clipboard2-pulse",
    },
    {
        "id": "wds-to-mpi",
        "label": "WDS → MPI",
        "source": "WDS",
        "source_port": 2582,
        "pre_queue_suffix": "sbq-wds-hl7-transformer",
        "post_queue_suffix": None,
        "transformer": None,
        "destination": "MPI",
        "colour": "#f97316",
        "icon": "bi-hospital",
    },
    {
        "id": "mpi-outbound",
        "label": "MPI Outbound",
        "source": "MPI",
        "source_port": 2580,
        "topic_suffix": "sbt-mpi-hl7-input",
        "transformer": None,
        "destination": "Downstream Systems",
        "colour": "#f59e0b",
        "icon": "bi-broadcast",
    },
]


def _resolve_flows_from_suffix(queue_names: list[str], topic_names: list[str]) -> dict[str, dict]:
    """Fallback: build the FLOWS dict by resolving queue/topic names via suffix matching."""

    flows: dict[str, dict] = {}
    for defn in _FLOW_DEFS:
        # --- Topic-based flow (MPI Outbound) ---
        if "topic_suffix" in defn:
            topic_name = resolve_by_suffix(topic_names, defn["topic_suffix"]) if defn["topic_suffix"] else None
            subscriptions: list[dict] = []
            if topic_name:
                subscriptions = get_subscriptions(topic_name)
                log.info("Topic %s has %d subscriptions", topic_name, len(subscriptions))

            flows[defn["id"]] = {
                "label": defn["label"],
                "source": defn["source"],
                "source_port": defn["source_port"],
                "source_host": None,
                "destination_host": None,
                "destination_port": None,
                "pre_queue": None,
                "transformer": defn["transformer"],
                "post_queue": None,
                "topic": topic_name,
                "subscriptions": subscriptions,
                "destination": defn["destination"],
                "colour": defn["colour"],
                "icon": defn["icon"],
            }
            continue

        # --- Queue-based flow (standard) ---
        pre_suffix = defn.get("pre_queue_suffix")
        post_suffix = defn.get("post_queue_suffix")

        pre_queue = resolve_by_suffix(queue_names, pre_suffix) if pre_suffix else None
        post_queue = resolve_by_suffix(queue_names, post_suffix) if post_suffix else None

        flows[defn["id"]] = {
            "label": defn["label"],
            "source": defn["source"],
            "source_port": defn["source_port"],
            "source_host": None,
            "destination_host": None,
            "destination_port": None,
            "pre_queue": pre_queue,
            "transformer": defn["transformer"],
            "post_queue": post_queue,
            "destination": defn["destination"],
            "colour": defn["colour"],
            "icon": defn["icon"],
        }
    return flows


def _enrich_with_subscriptions(flows: dict[str, dict]) -> None:
    """Enrich each topic-based flow's own subscriptions with live Service Bus counts.

    ``get_subscriptions(topic)`` returns *every* subscription on the topic, and a
    topic may be shared by several flows, so the per-flow ownership filtering in
    :func:`_merge_subscription_records` is what keeps a subscription from
    appearing under a flow that does not own it.
    """

    consumers_by_topic = get_subscription_consumers_by_topic()

    for flow in flows.values():
        topic = flow.get("topic")
        if topic:
            subs = get_subscriptions(topic)
            flow["subscriptions"] = _merge_subscription_records(
                topic,
                flow.get("subscriptions", []),
                consumers_by_topic.get(topic, []),
                subs,
            )
            log.info("Topic %s has %d subscriptions", topic, len(subs))


def _merge_subscription_records(
    topic_name: str,
    flow_subscriptions: list[dict],
    consumer_subscriptions: list[dict],
    service_bus_subscriptions: list[dict],
) -> list[dict]:
    """Merge discovery metadata with Service Bus subscription counts.

    A single topic can be shared by more than one flow — e.g. the WDS server
    publishes to ``sbt-wds-hl7-input``, which is consumed independently by the
    WDS→MPI subscription sender and the WDS→WIS transformer.  Ownership is
    therefore taken from ``flow_subscriptions`` (the subscriptions Container App
    discovery attributed to *this* flow).  ``consumer_subscriptions`` and
    ``service_bus_subscriptions`` may list *every* subscription on the shared
    topic, so they are used only to enrich the owned subscriptions with consumer
    metadata and live counts — never to introduce a subscription that belongs to
    a different flow.
    """

    # Only subscriptions discovered for this flow are retained; this prevents a
    # subscription owned by one flow from leaking into every flow that shares
    # the topic.
    owned_names = {name for sub in flow_subscriptions if (name := sub.get("name"))}
    if not owned_names:
        return []

    merged: dict[str, dict] = {}

    def _seed(records: list[dict]) -> None:
        for record in records:
            name = record.get("name")
            if not name or name not in owned_names:
                continue
            current = merged.setdefault(
                name,
                {
                    "name": name,
                    "topic": topic_name,
                    "entity_name": f"{topic_name}/{name}",
                    "consumer_apps": [],
                },
            )
            for key, value in record.items():
                if key == "consumer_apps":
                    continue
                if value is not None:
                    current[key] = value
            existing_ids = {app.get("microservice_id") for app in current.get("consumer_apps", [])}
            for app in record.get("consumer_apps", []):
                microservice_id = app.get("microservice_id")
                if microservice_id in existing_ids:
                    continue
                current.setdefault("consumer_apps", []).append(app)
                existing_ids.add(microservice_id)

    _seed(flow_subscriptions)
    _seed(consumer_subscriptions)

    for sub in service_bus_subscriptions:
        name = sub.get("name")
        if not name or name not in owned_names:
            continue
        current = merged.setdefault(
            name,
            {
                "name": name,
                "topic": topic_name,
                "entity_name": f"{topic_name}/{name}",
                "consumer_apps": [],
            },
        )
        current.update(sub)
        current["topic"] = topic_name
        current["entity_name"] = f"{topic_name}/{name}"

    return [merged[name] for name in sorted(merged)]


# Module-level default — populated lazily on first access
FLOWS: dict[str, dict] = {}


def get_flows() -> dict[str, dict]:
    """Return flow definitions, preferring Container App discovery.

    1. Try ``arm.discover_flows()`` — reads WORKFLOW_ID and queue/topic env
       vars from every deployed Container App.
    2. Fall back to static ``_FLOW_DEFS`` with suffix-based queue matching
       if the Container Apps API is not configured or unreachable.

    Results are cached in the module-level ``FLOWS`` dict until
    ``refresh_flows()`` is called.
    """
    global FLOWS  # noqa: PLW0602
    if not FLOWS:
        refresh_flows()
    return FLOWS


def refresh_flows() -> dict[str, dict]:
    """Re-discover flows from Azure and update the cached FLOWS."""
    global FLOWS  # noqa: PLW0603

    # --- Demo mode: return synthetic flows without hitting Azure ---
    if config.DEMO_MODE:
        from dashboard.services.demo_data import DEMO_FLOWS  # noqa: PLC0415

        log.info("DEMO_MODE active — using %d synthetic flow(s)", len(DEMO_FLOWS))
        FLOWS = DEMO_FLOWS
        return FLOWS

    # --- Primary: Container App env var discovery ---
    discovered = discover_flows()
    if discovered:
        log.info("Using %d flow(s) from Container App discovery", len(discovered))
        _enrich_with_subscriptions(discovered)
        FLOWS = discovered
        return FLOWS

    # --- Fallback: static definitions + suffix matching ---
    log.info("Container App discovery unavailable — falling back to suffix matching")
    queue_names = get_queue_names()
    topic_names = get_topic_names()
    if queue_names or topic_names:
        log.info("Resolved %d queues and %d topics from Service Bus namespace", len(queue_names), len(topic_names))
        FLOWS = _resolve_flows_from_suffix(queue_names, topic_names)
    else:
        log.warning("No queues or topics found — using flow definitions without queue mapping")
        FLOWS = _resolve_flows_from_suffix([], [])
    return FLOWS


# ---------------------------------------------------------------------------
# Dynamic flow discovery
# ---------------------------------------------------------------------------


def get_active_flows(force_refresh: bool = False) -> dict[str, dict]:
    """
    Return flows that are currently deployed in Azure.

    When Container App discovery is active, all discovered flows are already
    filtered to deployed apps.  When using the static fallback, all statically
    defined flows are returned (no ARM tag filtering needed).

    Pass ``force_refresh=True`` to bypass caches (used by /api/refresh).
    """
    if force_refresh:
        refresh_flows()
    return get_flows()


# ---------------------------------------------------------------------------
# Health calculation helpers
# ---------------------------------------------------------------------------


def queue_health(active: int, dlq: int) -> str:
    """Return 'critical' | 'warning' | 'healthy' for a single queue."""
    if active >= config.QUEUE_CRITICAL_THRESHOLD:
        return "critical"
    if active >= config.QUEUE_WARNING_THRESHOLD or dlq >= config.DLQ_WARNING_THRESHOLD:
        return "warning"
    return "healthy"


def flow_health(
    flow_id: str,
    queues_by_name: dict[str, dict],
    flows: dict[str, dict] | None = None,
    topics_by_name: dict[str, dict] | None = None,
) -> str:
    """
    Return overall health for a flow given a mapping of queue-name → queue dict.
    Queue dicts must contain ``active_message_count`` and ``dead_letter_message_count``.

    For topic-based flows (MPI Outbound), health is derived from the
    subscription message counts stored directly in the flow definition, plus
    the backlog/dead-letter counts of the topic entity itself when a
    ``topics_by_name`` mapping is supplied.  A topic can be shared by several
    flows, so the topic entity's own backlog only counts towards the flow that
    *owns* the topic (the publisher, identified by ``source_port``); consumer
    flows on the same topic are judged solely on their subscription backlog.
    """
    if flows is None:
        flows = get_flows()
    flow = flows[flow_id]

    statuses: list[str] = []

    # Topic-based flow — check the topic entity's own backlog/DLQ, but only for
    # the flow that owns (publishes to) the topic to avoid counting a shared
    # topic's backlog against every consumer flow.
    topic_name = flow.get("topic")
    if topic_name and topics_by_name is not None and flow.get("source_port"):
        topic = topics_by_name.get(topic_name)
        if topic is None:
            statuses.append("unknown")
        else:
            statuses.append(
                queue_health(
                    topic.get("active_message_count", 0),
                    topic.get("dead_letter_message_count", 0),
                )
            )

    # Topic-based flow — check subscriptions
    subscriptions = flow.get("subscriptions", [])
    if subscriptions:
        for sub in subscriptions:
            if sub.get("status", "Unknown") == "Unknown":
                statuses.append("unknown")
                continue
            statuses.append(
                queue_health(
                    sub.get("active_message_count", 0),
                    sub.get("dead_letter_message_count", 0),
                )
            )

    # Queue-based or hybrid topic->queue flow — check pre/post queues too.
    relevant = [q for q in [flow.get("pre_queue"), flow.get("post_queue")] if q]
    for qname in relevant:
        q = queues_by_name.get(qname)
        if q is None:
            statuses.append("unknown")
            continue
        statuses.append(
            queue_health(
                q.get("active_message_count", 0),
                q.get("dead_letter_message_count", 0),
            )
        )
    if not statuses:
        return "unknown"
    if "critical" in statuses:
        return "critical"
    if "warning" in statuses:
        return "warning"
    if "unknown" in statuses:
        return "unknown"
    return "healthy"


def overall_health(flow_statuses: list[str]) -> str:
    """Roll up a list of per-flow health strings into one system-level status."""
    if "critical" in flow_statuses:
        return "critical"
    if "warning" in flow_statuses:
        return "warning"
    if all(s == "healthy" for s in flow_statuses):
        return "healthy"
    return "unknown"


def build_flow_options(flows: dict[str, dict], alarm_rules: list[dict]) -> list[dict[str, str]]:
    """Return flow picker options for discovered flows plus any workflow referenced only by an alarm rule."""
    labels: dict[str, str] = {fid: flow.get("label") or fid for fid, flow in flows.items()}
    for rule in alarm_rules:
        wid = (rule.get("workflow_id") or "").strip()
        if wid and wid not in labels:
            labels[wid] = wid
    return sorted(({"id": k, "label": v} for k, v in labels.items()), key=lambda o: o["label"].lower())


def queue_to_workflow_id(queue_name: str) -> str | None:
    """Map a queue name back to the workflow_id (flow ID) that owns it.

    Searches the active flow definitions for a flow whose ``pre_queue``
    or ``post_queue`` matches *queue_name* (case-insensitive).
    Returns ``None`` if no match is found.
    """
    return entity_to_workflow_id("queue", queue_name)


def entity_to_workflow_id(entity_type: str, entity_name: str) -> str | None:
    """Map a queue, topic, or topic subscription back to its owning workflow."""
    flows = get_flows()
    lower = entity_name.lower()
    entity_type_lower = entity_type.lower()
    for flow_id, flow in flows.items():
        pre = (flow.get("pre_queue") or "").lower()
        post = (flow.get("post_queue") or "").lower()
        topic = (flow.get("topic") or "").lower()

        if entity_type_lower == "queue" and lower in (pre, post):
            return flow_id
        if entity_type_lower == "topic" and topic == lower:
            return flow_id
        if entity_type_lower == "subscription" and "/" in entity_name:
            topic_name, subscription_name = entity_name.split("/", maxsplit=1)
            if topic != topic_name.lower():
                continue
            for sub in flow.get("subscriptions", []):
                if (sub.get("name") or "").lower() == subscription_name.lower():
                    return flow_id
    return None


def build_flow_data(
    queues: list[dict],
    flows: dict[str, dict] | None = None,
    topics: list[dict] | None = None,
) -> list[dict]:
    """
    Given the raw list of queue dicts from service_bus.get_queues(),
    return a list of enriched flow dicts ready for the template / API.

    Pass an explicit ``flows`` dict (e.g. from ``get_active_flows()``) to
    restrict output to deployed flows.  Defaults to all flows if omitted.

    Pass the ``topics`` list (from ``get_namespace_snapshot()`` /
    ``get_topics()``) so topic-level backlog and dead-letter counts feed into
    each flow's health and per-flow totals.
    """
    if flows is None:
        flows = get_flows()
    queues_by_name: dict[str, dict] = {q["name"]: q for q in queues}
    topics_by_name: dict[str, dict] | None = None if topics is None else {t["name"]: t for t in topics}

    result = []
    for flow_id, flow in flows.items():
        pre_q = queues_by_name.get(flow.get("pre_queue", ""))
        post_q = queues_by_name.get(flow.get("post_queue", ""))
        subscriptions = flow.get("subscriptions", [])
        topic_name = flow.get("topic")
        topic = (topics_by_name or {}).get(topic_name or "")
        if topic_name and topic is not None:
            subscriptions = _merge_subscription_records(
                topic_name,
                subscriptions,
                [],
                topic.get("subscriptions", []),
            )
        flow_with_subscriptions = {**flow, "subscriptions": subscriptions}

        health = flow_health(flow_id, queues_by_name, {flow_id: flow_with_subscriptions}, topics_by_name)

        # Topic backlog/DLQ only counts for the flow that owns (publishes to)
        # the topic; a shared topic must not be counted against consumer flows.
        owns_topic = bool(topic_name and flow.get("source_port"))
        topic_summary = (
            _topic_summary(topic_name, (topics_by_name or {}).get(topic_name or ""))
            if owns_topic
            else _topic_summary(topic_name if flow.get("source_port") else None, None)
        )

        # Build subscription summaries for topic-based flows
        sub_summaries = []
        for sub in subscriptions:
            active = sub.get("active_message_count", 0)
            dlq = sub.get("dead_letter_message_count", 0)
            sub_summaries.append(
                {
                    "name": sub["name"],
                    "topic": sub.get("topic") or topic_name,
                    "entity_type": "subscription",
                    "entity_name": (
                        sub.get("entity_name")
                        or f"{topic_name}/{sub['name']}"
                        if topic_name
                        else sub["name"]
                    ),
                    "active": active,
                    "dlq": dlq,
                    "status": sub.get("status", "Unknown"),
                    "message_count": sub.get("message_count", 0),
                    "consumer_apps": sub.get("consumer_apps", []),
                    "health": (
                        "unknown"
                        if sub.get("status", "Unknown") == "Unknown"
                        else queue_health(active, dlq)
                    ),
                }
            )

        result.append(
            {
                "id": flow_id,
                "label": flow["label"],
                "source": flow["source"],
                "source_port": flow.get("source_port"),
                "transformer": flow.get("transformer"),
                "destination": flow["destination"],
                "colour": flow["colour"],
                "icon": flow["icon"],
                "health": health,
                "pre_queue": _queue_summary(flow.get("pre_queue"), pre_q),
                "post_queue": _queue_summary(flow.get("post_queue"), post_q),
                "topic": topic_name,
                "topic_summary": topic_summary,
                "subscriptions": sub_summaries,
            }
        )
    return result


def _queue_summary(name: str | None, q: dict | None) -> dict:
    if not name:
        return {
            "name": None,
            "entity_type": "queue",
            "entity_name": None,
            "active": 0,
            "dlq": 0,
            "health": "healthy",
            "exists": False,
        }
    if q is None:
        return {
            "name": name,
            "entity_type": "queue",
            "entity_name": name,
            "active": 0,
            "dlq": 0,
            "health": "unknown",
            "exists": False,
        }
    active = q.get("active_message_count", 0)
    dlq = q.get("dead_letter_message_count", 0)
    return {
        "name": name,
        "entity_type": "queue",
        "entity_name": name,
        "active": active,
        "dlq": dlq,
        "status": q.get("status", "Unknown"),
        "health": queue_health(active, dlq),
        "exists": True,
    }


def _topic_summary(name: str | None, topic: dict | None) -> dict:
    """Summarise a flow's topic entity (backlog/DLQ) for template + totals use."""
    if not name:
        return {
            "name": None,
            "entity_type": "topic",
            "entity_name": None,
            "active": 0,
            "dlq": 0,
            "health": "healthy",
            "exists": False,
        }
    if topic is None:
        return {
            "name": name,
            "entity_type": "topic",
            "entity_name": name,
            "active": 0,
            "dlq": 0,
            "health": "unknown",
            "exists": False,
        }
    active = topic.get("active_message_count", 0)
    dlq = topic.get("dead_letter_message_count", 0)
    return {
        "name": name,
        "entity_type": "topic",
        "entity_name": name,
        "active": active,
        "dlq": dlq,
        "health": queue_health(active, dlq),
        "exists": True,
    }
