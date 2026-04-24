"""
Azure Service Bus queue metrics via azure-mgmt-servicebus.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from dashboard import config
from dashboard.services.credentials import get_azure_credential

log = logging.getLogger(__name__)


def _get_client():
    from azure.mgmt.servicebus import ServiceBusManagementClient

    cred = get_azure_credential()
    return ServiceBusManagementClient(cred, config.AZURE_SUBSCRIPTION_ID)


def get_queues() -> list[dict]:
    """
    Return a list of queue dicts. Falls back to an empty list if required
    Service Bus resource configuration is missing.
    """
    if not all([config.AZURE_SUBSCRIPTION_ID, config.AZURE_RESOURCE_GROUP, config.AZURE_SERVICE_BUS_NAMESPACE]):
        log.warning("Service Bus resource configuration missing — returning empty list")
        return []

    try:
        client = _get_client()
        queues = client.queues.list_by_namespace(
            config.AZURE_RESOURCE_GROUP,
            config.AZURE_SERVICE_BUS_NAMESPACE,
        )
        result = []
        for q in queues:
            result.append(
                {
                    "name": q.name,
                    "status": str(q.status) if q.status else "Unknown",
                    "active_message_count": (
                        q.count_details.active_message_count
                        if q.count_details
                        else 0
                    ) or 0,
                    "dead_letter_message_count": (
                        q.count_details.dead_letter_message_count
                        if q.count_details
                        else 0
                    ) or 0,
                    "scheduled_message_count": (
                        q.count_details.scheduled_message_count
                        if q.count_details
                        else 0
                    ) or 0,
                    "message_count": q.message_count or 0,
                    "size_in_bytes": q.size_in_bytes or 0,
                    "max_size_in_megabytes": q.max_size_in_megabytes or 0,
                }
            )
        return result
    except Exception as exc:
        log.error("Failed to fetch Service Bus queues: %s", exc)
        return []


@lru_cache(maxsize=1)
def get_queue_names() -> list[str]:
    """Return the list of queue names from the Service Bus namespace (cached)."""
    return [q["name"] for q in get_queues()]


def resolve_by_suffix(names: list[str], suffix: str) -> str | None:
    """Find a name ending with *suffix* (case-insensitive).

    The Terraform naming convention produces predictable suffixes such as
    ``-sbq-phw-hl7-transformer`` or ``-sbt-mpi-hl7-input``.  This is more
    reliable than keyword-contains matching because queue names like
    ``…-sbq-hl7-sender`` (PHW's generic sender queue) have no system prefix.
    """
    suffix_lower = suffix.lower()
    for name in names:
        if name.lower().endswith(suffix_lower):
            return name
    return None


# ---------------------------------------------------------------------------
# Topic & subscription helpers
# ---------------------------------------------------------------------------

def get_topics() -> list[dict]:
    """Return a list of topic dicts from the Service Bus namespace."""
    if not all([config.AZURE_SUBSCRIPTION_ID, config.AZURE_RESOURCE_GROUP, config.AZURE_SERVICE_BUS_NAMESPACE]):
        return []

    try:
        client = _get_client()
        topics = client.topics.list_by_namespace(
            config.AZURE_RESOURCE_GROUP,
            config.AZURE_SERVICE_BUS_NAMESPACE,
        )
        return [
            {
                "name": t.name,
                "status": str(t.status) if t.status else "Unknown",
                "active_message_count": (
                    t.count_details.active_message_count if t.count_details else 0
                ) or 0,
                "dead_letter_message_count": (
                    t.count_details.dead_letter_message_count if t.count_details else 0
                ) or 0,
                "scheduled_message_count": (
                    t.count_details.scheduled_message_count if t.count_details else 0
                ) or 0,
                "subscription_count": t.subscription_count or 0,
                "size_in_bytes": t.size_in_bytes or 0,
                "max_size_in_megabytes": t.max_size_in_megabytes or 0,
            }
            for t in topics
        ]
    except Exception as exc:
        log.error("Failed to fetch Service Bus topics: %s", exc)
        return []


@lru_cache(maxsize=1)
def get_topic_names() -> list[str]:
    """Return topic names from the namespace (cached)."""
    return [t["name"] for t in get_topics()]


def get_subscriptions(topic_name: str) -> list[dict]:
    """Return subscription dicts for a given topic."""
    if not all([config.AZURE_SUBSCRIPTION_ID, config.AZURE_RESOURCE_GROUP, config.AZURE_SERVICE_BUS_NAMESPACE]):
        return []

    try:
        client = _get_client()
        subs = client.subscriptions.list_by_topic(
            config.AZURE_RESOURCE_GROUP,
            config.AZURE_SERVICE_BUS_NAMESPACE,
            topic_name,
        )
        return [
            {
                "name": s.name,
                "status": str(s.status) if s.status else "Unknown",
                "active_message_count": (
                    s.count_details.active_message_count if s.count_details else 0
                ) or 0,
                "dead_letter_message_count": (
                    s.count_details.dead_letter_message_count if s.count_details else 0
                ) or 0,
                "message_count": s.message_count or 0,
            }
            for s in subs
        ]
    except Exception as exc:
        log.error("Failed to fetch subscriptions for topic %s: %s", topic_name, exc)
        return []


# ---------------------------------------------------------------------------
# Service Bus metrics (Incoming / Outgoing messages over time)
# ---------------------------------------------------------------------------

def get_message_metrics(timespan_hours: int = 1, queue_name: str | None = None) -> dict:
    """Query Log Analytics for Service Bus IncomingMessages / OutgoingMessages.

    Uses a KQL query against the ``AzureMetrics`` table rather than the
    Azure Monitor Metrics REST API, because the installed SDK only ships
    the ``LogsQueryClient``.

    If *queue_name* is provided the results are scoped to that single queue.

    Returns a dict with ``incoming`` and ``outgoing`` lists of
    ``{"time": ISO-string, "value": int}`` data points, plus a
    ``timespan`` label.
    """
    empty: dict = {"incoming": [], "outgoing": [], "timespan": f"{timespan_hours}h"}

    workspace_id = config.AZURE_LOG_ANALYTICS_WORKSPACE_ID
    if not workspace_id:
        log.warning("Log Analytics workspace not configured — skipping message metrics")
        return empty

    # Choose bin size based on timespan
    if timespan_hours <= 1:
        bin_size = "1m"
    elif timespan_hours <= 12:
        bin_size = "5m"
    elif timespan_hours <= 48:
        bin_size = "15m"
    else:
        bin_size = "1h"

    import re

    queue_filter_kql = ""
    if queue_name:
        safe_queue = re.sub(r"[^a-zA-Z0-9\-_]", "", queue_name)
        queue_filter_kql = f"| where Resource =~ '{safe_queue}'\n"

    kql = (
        "AzureMetrics\n"
        "| where ResourceProvider == 'MICROSOFT.SERVICEBUS'\n"
        "| where MetricName in ('IncomingMessages', 'OutgoingMessages')\n"
        f"| where TimeGenerated > ago({timespan_hours}h)\n"
        f"{queue_filter_kql}"
        f"| summarize Value=sum(Total) by bin(TimeGenerated, {bin_size}), MetricName\n"
        "| order by TimeGenerated asc\n"
    )

    try:
        from azure.monitor.query import LogsQueryClient, LogsQueryStatus

        cred = get_azure_credential()
        client = LogsQueryClient(cred)

        response = client.query_workspace(
            workspace_id=workspace_id,
            query=kql,
            timespan=timedelta(hours=timespan_hours),
        )

        if response.status != LogsQueryStatus.SUCCESS:
            log.error("Log Analytics query failed: %s", response.partial_error)
            return empty

        series: dict[str, list[dict]] = {"incoming": [], "outgoing": []}
        key_map = {"IncomingMessages": "incoming", "OutgoingMessages": "outgoing"}

        for row in response.tables[0].rows:
            time_generated = row[0]  # datetime
            metric_name = row[1]     # str
            value = row[2]           # float/int

            key = key_map.get(metric_name)
            if not key:
                continue

            if isinstance(time_generated, datetime):
                time_str = time_generated.astimezone(timezone.utc).isoformat()
            else:
                time_str = str(time_generated)

            series[key].append({
                "time": time_str,
                "value": int(value) if value is not None else 0,
            })

        series["timespan"] = f"{timespan_hours}h"
        log.info(
            "Fetched %d incoming, %d outgoing message metric points",
            len(series["incoming"]),
            len(series["outgoing"]),
        )
        return series

    except Exception as exc:
        log.error("Failed to fetch Service Bus message metrics: %s", exc)
        return empty
