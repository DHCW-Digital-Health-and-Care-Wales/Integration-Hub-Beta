"""
Azure Container Apps metrics — thin wrapper around azure_monitor.get_container_app_metrics().
Provides grouping by integration flow.

When Container App discovery is active, the app-to-flow mapping is derived
from the discovered WORKFLOW_ID env vars.  Otherwise falls back to a
keyword-based mapping.
"""

from __future__ import annotations

import logging

import dashboard.services.arm as arm
from dashboard.services.azure_monitor import get_container_app_metrics
from dashboard.services.flows import get_flows

log = logging.getLogger(__name__)

# Fallback mapping used when Container App discovery is not available.
_FALLBACK_APP_FLOW_MAP: dict[str, str] = {
    "phw": "phw-to-mpi",
    "paris": "paris-to-mpi",
    "chemo": "chemocare-to-mpi",
    "pims": "pims-to-mpi",
    "mosaiq": "mosaiq-to-mpi",
    "mpi": "mpi-outbound",
    "wds": "wds-to-mpi",
}


def _build_app_flow_map() -> dict[str, str]:
    """Build a Container-App-name → flow_id mapping from discovered flows.

    Container App discovery stores the app names that belong to each flow.
    If discovery was used, we can build an exact mapping.  If not, we
    return an empty dict and the caller falls back to keyword matching.
    """
    try:
        flows = arm.discover_flows()
        if not arm._cached_apps:
            return {}

        topic_owner_flow_map = {
            flow["topic"]: flow_id
            for flow_id, flow in flows.items()
            if flow.get("topic") and flow.get("source_port")
        }

        app_flow_map: dict[str, str] = {}
        for app in arm._cached_apps:
            name = app.get("name")
            env = app.get("env", {})
            workflow_id = env.get("WORKFLOW_ID")
            if not name or not workflow_id:
                continue

            if workflow_id not in flows:
                topic_name = env.get("INGRESS_TOPIC_NAME") or env.get("EGRESS_TOPIC_NAME")
                workflow_id = topic_owner_flow_map.get(topic_name, workflow_id)

            app_flow_map[name] = workflow_id

        return app_flow_map
    except Exception:
        return {}


def _infer_flow(app_name: str) -> str | None:
    """Match a Container App name to a flow_id using keyword fragments."""
    lower = app_name.lower()
    for fragment, flow_id in _FALLBACK_APP_FLOW_MAP.items():
        if fragment in lower:
            return flow_id
    return None


def get_container_apps_metrics() -> dict[str, list[dict]]:
    """
    Return a dict keyed by flow_id → list of container app metric dicts.
    Apps that cannot be mapped to a flow are placed under 'other'.
    """
    raw = get_container_app_metrics()
    grouped: dict[str, list[dict]] = {fid: [] for fid in get_flows()}
    grouped["other"] = []
    app_flow_map = _build_app_flow_map()

    for app in raw:
        flow_id = app_flow_map.get(app["name"]) or _infer_flow(app["name"])
        if flow_id and flow_id in grouped:
            grouped[flow_id].append(app)
        else:
            grouped["other"].append(app)

    return grouped
