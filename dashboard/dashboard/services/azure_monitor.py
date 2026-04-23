"""
Azure Monitor / Log Analytics queries for the Integration Hub.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from dashboard import config
from dashboard.services.credentials import get_azure_credential

log = logging.getLogger(__name__)


def _get_logs_client():
    from azure.monitor.query import LogsQueryClient

    cred = get_azure_credential()
    return LogsQueryClient(cred)


def _credentials_configured() -> bool:
    return bool(config.AZURE_LOG_ANALYTICS_WORKSPACE_ID)


def get_exceptions(hours: int = 24) -> list[dict]:
    """
    Query Log Analytics for application exceptions in the last *hours* hours.
    Returns a list of exception dicts. Falls back to [] on any error.
    """
    if not _credentials_configured():
        log.warning("Log Analytics workspace not configured — returning empty list")
        return []

    query = f"""
    exceptions
    | where timestamp > ago({hours}h)
    | project timestamp, type, outerMessage, severityLevel, appName, operation_Id
    | order by timestamp desc
    | take 200
    """
    try:
        from azure.monitor.query import LogsQueryStatus

        client = _get_logs_client()
        response = client.query_workspace(
            workspace_id=config.AZURE_LOG_ANALYTICS_WORKSPACE_ID,
            query=query,
            timespan=timedelta(hours=hours),
        )
        if response.status != LogsQueryStatus.SUCCESS:
            log.error("Log Analytics query failed: %s", response.partial_error)
            return []

        results = []
        for table in response.tables:
            for row in table.rows:
                row_dict = dict(zip(table.columns, row))
                results.append(
                    {
                        "timestamp": str(row_dict.get("timestamp", "")),
                        "type": row_dict.get("type", "Unknown"),
                        "message": row_dict.get("outerMessage", ""),
                        "severity": int(row_dict.get("severityLevel", 3)),
                        "app": row_dict.get("appName", ""),
                        "operation_id": row_dict.get("operation_Id", ""),
                    }
                )
        return results
    except Exception as exc:
        log.error("Failed to fetch exceptions: %s", exc)
        return []


def get_messages_today() -> list[dict]:
    """
    Query Log Analytics for HL7 messages processed today.
    Returns a list of message dicts.
    """
    if not _credentials_configured():
        log.warning("Log Analytics credentials not configured — returning empty list")
        return []

    query = """
    customEvents
    | where timestamp > startofday(now())
    | where name == "MessageProcessed" or name startswith "HL7"
    | project timestamp, name, customDimensions, appName
    | order by timestamp desc
    | take 500
    """
    try:
        from azure.monitor.query import LogsQueryStatus

        client = _get_logs_client()
        response = client.query_workspace(
            workspace_id=config.AZURE_LOG_ANALYTICS_WORKSPACE_ID,
            query=query,
            timespan=timedelta(hours=24),
        )
        if response.status != LogsQueryStatus.SUCCESS:
            return []

        results = []
        for table in response.tables:
            for row in table.rows:
                row_dict = dict(zip(table.columns, row))
                results.append(
                    {
                        "timestamp": str(row_dict.get("timestamp", "")),
                        "event": row_dict.get("name", ""),
                        "app": row_dict.get("appName", ""),
                        "dimensions": row_dict.get("customDimensions", {}),
                    }
                )
        return results
    except Exception as exc:
        log.error("Failed to fetch messages: %s", exc)
        return []


def get_container_app_metrics() -> list[dict]:
    """
    Query Azure Monitor metrics for Container Apps CPU and memory utilisation.
    Groups results by app name.  Falls back to [] on any error.
    """
    if not all(
        [
            config.AZURE_SUBSCRIPTION_ID,
            config.AZURE_CONTAINER_APPS_RESOURCE_GROUP,
            config.AZURE_CONTAINER_APPS_ENVIRONMENT,
        ]
    ):
        log.warning("Container Apps resource configuration missing — returning empty list")
        return []

    try:
        from azure.monitor.query import MetricsQueryClient
        from azure.mgmt.appcontainers import ContainerAppsAPIClient

        cred = get_azure_credential()
        apps_client = ContainerAppsAPIClient(cred, config.AZURE_SUBSCRIPTION_ID)
        metrics_client = MetricsQueryClient(cred)

        apps = list(
            apps_client.container_apps.list_by_resource_group(
                config.AZURE_CONTAINER_APPS_RESOURCE_GROUP
            )
        )

        results = []
        for app in apps:
            resource_id = app.id
            try:
                response = metrics_client.query_resource(
                    resource_uri=resource_id,
                    metric_names=["CpuUsage", "MemoryWorkingSetBytes", "Replicas"],
                    timespan=timedelta(minutes=5),
                    granularity=timedelta(minutes=1),
                    aggregations=["Average", "Maximum"],
                )
                metrics: dict = {}
                for m in response.metrics:
                    for ts in m.timeseries:
                        for dp in reversed(ts.data):
                            val = dp.average if dp.average is not None else dp.maximum
                            if val is not None:
                                metrics[m.name] = round(val, 2)
                                break
                results.append(
                    {
                        "name": app.name,
                        "location": app.location,
                        "cpu_usage": metrics.get("CpuUsage", 0),
                        "memory_bytes": metrics.get("MemoryWorkingSetBytes", 0),
                        "replicas": int(metrics.get("Replicas", 0)),
                    }
                )
            except Exception as inner:
                log.warning("Could not get metrics for %s: %s", app.name, inner)
                results.append({"name": app.name, "cpu_usage": 0, "memory_bytes": 0, "replicas": 0})

        return results
    except Exception as exc:
        log.error("Failed to fetch Container App metrics: %s", exc)
        return []
