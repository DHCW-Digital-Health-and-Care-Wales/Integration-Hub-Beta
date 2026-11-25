"""
Azure Container Apps metrics — thin wrapper around azure_monitor.get_container_app_metrics().
Provides grouping by integration flow.

When Container App discovery is active, the app-to-flow mapping is derived
from the discovered flow membership (``integration-hub-flow`` tag, falling back
to ``WORKFLOW_ID``); an app shared by several flows is listed under each.
Otherwise falls back to a keyword-based mapping.
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


def _build_app_flow_map() -> dict[str, list[str]]:
    """Build a Container-App-name → flow IDs mapping from discovered flows.

    Container App discovery stores the flow IDs each app belongs to.  If
    discovery was used, we can build an exact mapping.  If not, we return an
    empty dict and the caller falls back to keyword matching.
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

        app_flow_map: dict[str, list[str]] = {}
        for app in arm._cached_apps:
            name = app.get("name")
            if not name:
                continue
            env = app.get("env", {})
            topic_name = env.get("INGRESS_TOPIC_NAME") or env.get("EGRESS_TOPIC_NAME")

            flow_ids: list[str] = []
            for discovered_id in arm.app_flow_ids(app):
                # Flows merged into their topic owner no longer exist on their own.
                flow_id = (
                    discovered_id if discovered_id in flows else topic_owner_flow_map.get(topic_name, discovered_id)
                )
                if flow_id not in flow_ids:
                    flow_ids.append(flow_id)
            if flow_ids:
                app_flow_map[name] = flow_ids

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
    An app shared by several flows appears under each of them.
    Apps that cannot be mapped to a flow are placed under 'other'.
    """
    raw = get_container_app_metrics()
    grouped: dict[str, list[dict]] = {fid: [] for fid in get_flows()}
    grouped["other"] = []
    app_flow_map = _build_app_flow_map()

    for app in raw:
        mapped = app_flow_map.get(app["name"])
        if not mapped:
            inferred = _infer_flow(app["name"])
            mapped = [inferred] if inferred else []
        flow_ids = [fid for fid in mapped if fid in grouped]
        if not flow_ids:
            grouped["other"].append(app)
        for flow_id in flow_ids:
            grouped[flow_id].append(app)

    return grouped
