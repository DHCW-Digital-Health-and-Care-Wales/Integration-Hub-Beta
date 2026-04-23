"""
Azure Resource Manager — discovers deployed Integration Hub flows from Container App tags.

Each Container App in a flow is tagged with ``integration-hub-flow = <flow-id>``
by Terraform.  This module queries ARM at startup (and periodically) to build the
set of flow IDs that are actually deployed, so the dashboard only shows live flows.
"""
from __future__ import annotations

import logging
import time
from threading import Lock

from dashboard import config

log = logging.getLogger(__name__)

# Tag key applied to every Container App by Terraform
FLOW_TAG_KEY = "integration-hub-flow"

# Cache: re-query ARM at most once per TTL (default 5 minutes)
_CACHE_TTL_SECONDS = 300
_cache_lock = Lock()
_cached_flow_ids: set[str] = set()
_cache_timestamp: float = 0.0


def get_deployed_flow_ids(force: bool = False) -> set[str]:
    """
    Return the set of ``integration-hub-flow`` tag values found across all
    Container Apps in the configured resource group.

    Results are cached for ``_CACHE_TTL_SECONDS`` seconds to avoid hammering
    the ARM API on every page load.  Pass ``force=True`` to bypass the cache.

    Falls back to an empty set if credentials are not configured or ARM is
    unreachable, which causes the dashboard to display all statically-defined
    flows (safe degraded behaviour).
    """
    global _cached_flow_ids, _cache_timestamp

    if not _credentials_configured():
        log.warning("ARM credentials not fully configured — flow discovery disabled")
        return set()

    now = time.monotonic()
    with _cache_lock:
        if not force and (now - _cache_timestamp) < _CACHE_TTL_SECONDS:
            return set(_cached_flow_ids)

        flow_ids = _query_arm()
        _cached_flow_ids = flow_ids
        _cache_timestamp = now
        return set(flow_ids)


def _credentials_configured() -> bool:
    return all([
        config.AZURE_TENANT_ID,
        config.AZURE_CLIENT_ID,
        config.AZURE_CLIENT_SECRET,
        config.AZURE_SUBSCRIPTION_ID,
        config.AZURE_CONTAINER_APPS_RESOURCE_GROUP,
    ])


def _query_arm() -> set[str]:
    """Query ARM and return all unique flow IDs found in Container App tags."""
    try:
        from azure.identity import ClientSecretCredential
        from azure.mgmt.appcontainers import ContainerAppsAPIClient

        cred = ClientSecretCredential(
            tenant_id=config.AZURE_TENANT_ID,
            client_id=config.AZURE_CLIENT_ID,
            client_secret=config.AZURE_CLIENT_SECRET,
        )
        client = ContainerAppsAPIClient(cred, config.AZURE_SUBSCRIPTION_ID)
        apps = client.container_apps.list_by_resource_group(
            config.AZURE_CONTAINER_APPS_RESOURCE_GROUP
        )

        flow_ids: set[str] = set()
        for app in apps:
            tags = app.tags or {}
            flow_id = tags.get(FLOW_TAG_KEY)
            if flow_id:
                flow_ids.add(flow_id)

        log.info("ARM flow discovery found %d deployed flow(s): %s", len(flow_ids), sorted(flow_ids))
        return flow_ids

    except Exception as exc:
        log.error("ARM flow discovery failed: %s", exc)
        return set()
