"""
Flow definitions and health calculation for the Integration Hub.
Each flow represents an end-to-end HL7 message path.
"""
from __future__ import annotations

from dashboard import config

# ---------------------------------------------------------------------------
# Flow definitions
# ---------------------------------------------------------------------------

FLOWS: dict[str, dict] = {
    "phw-to-mpi": {
        "label": "PHW → MPI",
        "source": "PHW",
        "source_port": 2575,
        "pre_queue": config.QUEUE_PHW_PRE,
        "transformer": "PHW Transformer",
        "post_queue": config.QUEUE_PHW_POST,
        "destination": "MPI",
        "colour": "#3b82f6",
        "icon": "bi-heart-pulse",
    },
    "paris-to-mpi": {
        "label": "Paris → MPI",
        "source": "Paris",
        "source_port": 2577,
        "pre_queue": config.QUEUE_PARIS_PRE,
        "transformer": None,
        "post_queue": config.QUEUE_PARIS_POST,
        "destination": "MPI",
        "colour": "#a855f7",
        "icon": "bi-activity",
    },
    "chemocare-to-mpi": {
        "label": "ChemoCare → MPI",
        "source": "ChemoCare",
        "source_port": 2578,
        "pre_queue": config.QUEUE_CHEMO_PRE,
        "transformer": "Chemo Transformer",
        "post_queue": config.QUEUE_CHEMO_POST,
        "destination": "MPI",
        "colour": "#06b6d4",
        "icon": "bi-capsule",
    },
    "pims-to-mpi": {
        "label": "PIMS → MPI",
        "source": "PIMS",
        "source_port": 2579,
        "pre_queue": config.QUEUE_PIMS_PRE,
        "transformer": "PIMS Transformer",
        "post_queue": config.QUEUE_PIMS_POST,
        "destination": "MPI",
        "colour": "#22c55e",
        "icon": "bi-clipboard2-pulse",
    },
    "wds-to-mpi": {
        "label": "WDS → MPI",
        "source": "WDS",
        "source_port": 2582,
        "pre_queue": config.QUEUE_WDS_PRE,
        "transformer": None,
        "post_queue": config.QUEUE_WDS_POST,
        "destination": "MPI",
        "colour": "#f97316",
        "icon": "bi-hospital",
    },
    "mpi-outbound": {
        "label": "MPI Outbound",
        "source": "MPI",
        "source_port": 2580,
        "pre_queue": config.QUEUE_MPI_OUTBOUND,
        "transformer": None,
        "post_queue": None,
        "destination": "Downstream Systems",
        "colour": "#f59e0b",
        "icon": "bi-broadcast",
    },
}


# ---------------------------------------------------------------------------
# Dynamic flow discovery
# ---------------------------------------------------------------------------

def get_active_flows(force_refresh: bool = False) -> dict[str, dict]:
    """
    Return the subset of FLOWS that are currently deployed in Azure.

    Queries ARM for Container Apps tagged with ``integration-hub-flow`` and
    filters ``FLOWS`` to only those present.  If ARM is not reachable or
    returns nothing (e.g. local dev with no credentials), all flows are
    returned so the dashboard still works.

    Results from ARM are cached for 5 minutes — pass ``force_refresh=True``
    to bypass the cache (used by the /api/refresh endpoint).
    """
    from dashboard.services.arm import get_deployed_flow_ids

    deployed = get_deployed_flow_ids(force=force_refresh)
    if not deployed:
        # ARM not configured or unreachable — show everything
        return FLOWS

    active = {fid: flow for fid, flow in FLOWS.items() if fid in deployed}
    if not active:
        # Tags returned but none matched known flows — safe fallback
        return FLOWS

    return active


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
    """
    if flows is None:
        flows = FLOWS
    flow = flows[flow_id]
    relevant = [q for q in [flow.get("pre_queue"), flow.get("post_queue")] if q]
    statuses = []
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


def build_flow_data(queues: list[dict], flows: dict[str, dict] | None = None) -> list[dict]:
    """
    Given the raw list of queue dicts from service_bus.get_queues(),
    return a list of enriched flow dicts ready for the template / API.

    Pass an explicit ``flows`` dict (e.g. from ``get_active_flows()``) to
    restrict output to deployed flows.  Defaults to all ``FLOWS`` if omitted.
    """
    if flows is None:
        flows = FLOWS
    queues_by_name: dict[str, dict] = {q["name"]: q for q in queues}

    result = []
    for flow_id, flow in flows.items():
        pre_q = queues_by_name.get(flow.get("pre_queue", ""))
        post_q = queues_by_name.get(flow.get("post_queue", ""))

        health = flow_health(flow_id, queues_by_name, flows)

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
