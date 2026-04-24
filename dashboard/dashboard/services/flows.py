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
    from dashboard.services.service_bus import get_subscriptions, resolve_by_suffix

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
            "pre_queue": pre_queue,
            "transformer": defn["transformer"],
            "post_queue": post_queue,
            "destination": defn["destination"],
            "colour": defn["colour"],
            "icon": defn["icon"],
        }
    return flows


def _enrich_with_subscriptions(flows: dict[str, dict]) -> None:
    """For flows that have a topic, fetch subscriptions from Service Bus."""
    from dashboard.services.service_bus import get_subscriptions

    for flow in flows.values():
        topic = flow.get("topic")
        if topic and not flow.get("subscriptions"):
            subs = get_subscriptions(topic)
            flow["subscriptions"] = subs
            log.info("Topic %s has %d subscriptions", topic, len(subs))


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
    global FLOWS  # noqa: PLW0603
    if not FLOWS:
        refresh_flows()
    return FLOWS


def refresh_flows() -> dict[str, dict]:
    """Re-discover flows from Azure and update the cached FLOWS."""
    global FLOWS  # noqa: PLW0603

    # --- Primary: Container App env var discovery ---
    from dashboard.services.arm import discover_flows

    discovered = discover_flows()
    if discovered:
        log.info("Using %d flow(s) from Container App discovery", len(discovered))
        _enrich_with_subscriptions(discovered)
        FLOWS = discovered
        return FLOWS

    # --- Fallback: static definitions + suffix matching ---
    from dashboard.services.service_bus import get_queue_names, get_topic_names

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


def flow_health(flow_id: str, queues_by_name: dict[str, dict], flows: dict[str, dict] | None = None) -> str:
    """
    Return overall health for a flow given a mapping of queue-name → queue dict.
    Queue dicts must contain ``active_message_count`` and ``dead_letter_message_count``.

    For topic-based flows (MPI Outbound), health is derived from the
    subscription message counts stored directly in the flow definition.
    """
    if flows is None:
        flows = get_flows()
    flow = flows[flow_id]

    statuses: list[str] = []

    # Topic-based flow — check subscriptions
    subscriptions = flow.get("subscriptions", [])
    if subscriptions:
        for sub in subscriptions:
            statuses.append(
                queue_health(
                    sub.get("active_message_count", 0),
                    sub.get("dead_letter_message_count", 0),
                )
            )
    else:
        # Queue-based flow — check pre/post queues
        relevant = [q for q in [flow.get("pre_queue"), flow.get("post_queue")] if q]
        for qname in relevant:
            q = queues_by_name.get(qname)
            if q is None:
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


def queue_to_workflow_id(queue_name: str) -> str | None:
    """Map a queue name back to the workflow_id (flow ID) that owns it.

    Searches the active flow definitions for a flow whose ``pre_queue``
    or ``post_queue`` matches *queue_name* (case-insensitive).
    Returns ``None`` if no match is found.
    """
    flows = get_flows()
    lower = queue_name.lower()
    for flow_id, flow in flows.items():
        pre = (flow.get("pre_queue") or "").lower()
        post = (flow.get("post_queue") or "").lower()
        if lower in (pre, post):
            return flow_id
    return None


def build_flow_data(queues: list[dict], flows: dict[str, dict] | None = None) -> list[dict]:
    """
    Given the raw list of queue dicts from service_bus.get_queues(),
    return a list of enriched flow dicts ready for the template / API.

    Pass an explicit ``flows`` dict (e.g. from ``get_active_flows()``) to
    restrict output to deployed flows.  Defaults to all flows if omitted.
    """
    if flows is None:
        flows = get_flows()
    queues_by_name: dict[str, dict] = {q["name"]: q for q in queues}

    result = []
    for flow_id, flow in flows.items():
        pre_q = queues_by_name.get(flow.get("pre_queue", ""))
        post_q = queues_by_name.get(flow.get("post_queue", ""))

        health = flow_health(flow_id, queues_by_name, flows)

        # Build subscription summaries for topic-based flows
        sub_summaries = []
        for sub in flow.get("subscriptions", []):
            active = sub.get("active_message_count", 0)
            dlq = sub.get("dead_letter_message_count", 0)
            sub_summaries.append({
                "name": sub["name"],
                "active": active,
                "dlq": dlq,
                "health": queue_health(active, dlq),
            })

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
                "topic": flow.get("topic"),
                "subscriptions": sub_summaries,
            }
        )
    return result


def _queue_summary(name: str | None, q: dict | None) -> dict:
    if not name:
        return {"name": None, "active": 0, "dlq": 0, "health": "healthy", "exists": False}
    if q is None:
        return {"name": name, "active": 0, "dlq": 0, "health": "unknown", "exists": False}
    active = q.get("active_message_count", 0)
    dlq = q.get("dead_letter_message_count", 0)
    return {
        "name": name,
        "active": active,
        "dlq": dlq,
        "health": queue_health(active, dlq),
        "exists": True,
    }
