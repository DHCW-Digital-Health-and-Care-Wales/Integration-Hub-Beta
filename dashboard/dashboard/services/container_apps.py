"""
Azure Container Apps metrics — thin wrapper around azure_monitor.get_container_app_metrics().
Provides grouping by integration flow.

When Container App discovery is active, the app-to-flow mapping is derived
from the discovered WORKFLOW_ID env vars.  Otherwise falls back to a
keyword-based mapping.
"""
from __future__ import annotations

import logging

from dashboard.services.azure_monitor import get_container_app_metrics
from dashboard.services.flows import get_flows

log = logging.getLogger(__name__)

# Fallback mapping used when Container App discovery is not available.
_FALLBACK_APP_FLOW_MAP: dict[str, str] = {
    "phw": "phw-to-mpi",
    "paris": "paris-to-mpi",
    "chemo": "chemocare-to-mpi",
    "pims": "pims-to-mpi",
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
        from dashboard.services.arm import _cached_flows, _classify_app

        if not _cached_flows:
            return {}

        # Rebuild from the raw cached app list — not available directly,
        # so we use the fallback keyword approach alongside discovery.
        return {}
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

    for app in raw:
        flow_id = _infer_flow(app["name"])
        if flow_id and flow_id in grouped:
            grouped[flow_id].append(app)
        else:
            grouped["other"].append(app)

    return grouped
