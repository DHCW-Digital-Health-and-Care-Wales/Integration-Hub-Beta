"""
Azure Container Apps metrics — thin wrapper around azure_monitor.get_container_app_metrics().
Provides grouping by integration flow.
"""
from __future__ import annotations

import logging
from services.azure_monitor import get_container_app_metrics
from services.flows import FLOWS

log = logging.getLogger(__name__)

# Mapping of partial container-app name → flow id (adjust to actual naming)
_APP_FLOW_MAP: dict[str, str] = {
    "phw": "phw-to-mpi",
    "paris": "paris-to-mpi",
    "chemo": "chemocare-to-mpi",
    "pims": "pims-to-mpi",
    "mpi": "mpi-outbound",
}


def _infer_flow(app_name: str) -> str | None:
    lower = app_name.lower()
    for fragment, flow_id in _APP_FLOW_MAP.items():
        if fragment in lower:
            return flow_id
    return None


def get_container_apps_metrics() -> dict[str, list[dict]]:
    """
    Return a dict keyed by flow_id → list of container app metric dicts.
    Apps that cannot be mapped to a flow are placed under 'other'.
    """
    raw = get_container_app_metrics()
    grouped: dict[str, list[dict]] = {fid: [] for fid in FLOWS}
    grouped["other"] = []

    for app in raw:
        flow_id = _infer_flow(app["name"])
        if flow_id and flow_id in grouped:
            grouped[flow_id].append(app)
        else:
            grouped["other"].append(app)

    return grouped
