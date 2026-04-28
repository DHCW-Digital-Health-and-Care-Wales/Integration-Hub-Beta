"""
Azure Monitor / Log Analytics queries for the Integration Hub.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import timedelta
from typing import Any

from azure.monitor.query import LogsQueryClient, LogsQueryStatus

from dashboard import config
from dashboard.services.credentials import get_azure_credential

log = logging.getLogger(__name__)


def _get_logs_client() -> Any:
    cred = get_azure_credential()
    return LogsQueryClient(cred)


def _credentials_configured() -> bool:
    return bool(config.AZURE_LOG_ANALYTICS_WORKSPACE_ID)


def _parse_dimensions(raw_dimensions: object) -> dict:
    if isinstance(raw_dimensions, dict):
        return raw_dimensions

    if isinstance(raw_dimensions, str):
        try:
            parsed = json.loads(raw_dimensions)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    return {}


def get_exceptions(hours: int = 24) -> list[dict]:
    """
    Query Log Analytics for application exceptions in the last *hours* hours.
    Returns a list of exception dicts. Falls back to [] on any error.
    """
    if config.DEMO_MODE:
        from dashboard.services.demo_data import DEMO_EXCEPTIONS  # noqa: PLC0415
        return DEMO_EXCEPTIONS

    if not _credentials_configured():
        log.warning("Log Analytics workspace not configured — returning empty list")
        return []

    query = f"""
    AppExceptions
    | where TimeGenerated > ago({hours}h)
    | project timestamp=TimeGenerated,
              type=ExceptionType,
              outerMessage=coalesce(OuterMessage, Message),
              severityLevel=SeverityLevel,
              appName=AppRoleName,
              operation_Id=OperationId
    | order by timestamp desc
    | take 200
    """
    try:
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
                        "severity": int(row_dict.get("severityLevel") or 3),
                        "app": row_dict.get("appName", ""),
                        "operation_id": row_dict.get("operation_Id", ""),
                    }
                )
        return results
    except Exception as exc:
        log.error("Failed to fetch exceptions: %s", exc)
        return []


def get_messages_today(
    workflow_id: str | None = None,
    microservice_ids: list[str] | None = None,
) -> list[dict]:
    """
    Query Log Analytics for HL7 messages processed today.
    Returns a list of message dicts.

    If *microservice_ids* is given, only messages whose ``microservice_id``
    custom dimension matches one of the values are returned.
    Falls back to *workflow_id* filtering if *microservice_ids* is empty.
    """
    if not _credentials_configured():
        log.warning("Log Analytics credentials not configured — returning empty list")
        return []

    # Build the optional filter clause
    wf_filter = ""
    if microservice_ids:
        # Sanitise each id — only allow alphanumeric, hyphens, underscores
        safe_ids = [re.sub(r"[^a-zA-Z0-9\-_]", "", mid) for mid in microservice_ids]
        safe_ids = [s for s in safe_ids if s]
        if safe_ids:
            conditions = " or ".join(f'Properties contains "{sid}"' for sid in safe_ids)
            wf_filter = f"\n    | where {conditions}"
    elif workflow_id:
        safe_wf = re.sub(r"[^a-zA-Z0-9\-_]", "", workflow_id)
        wf_filter = f'\n    | where Properties contains "{safe_wf}"'

    query = f"""
    AppTraces
    | where TimeGenerated > startofday(now())
    | where Message == "Integration Hub Event"{wf_filter}
    | project timestamp=TimeGenerated,
              name=Message,
              customDimensions=Properties,
              appName=AppRoleName
    | order by timestamp desc
    | take 500
    """
    try:
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
                dimensions = _parse_dimensions(row_dict.get("customDimensions", {}))
                results.append(
                    {
                        "timestamp": str(row_dict.get("timestamp", "")),
                        "event": dimensions.get("event_type") or row_dict.get("name", ""),
                        "app": dimensions.get("microservice_id") or row_dict.get("appName", ""),
                        "dimensions": dimensions,
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
        from azure.mgmt.appcontainers import ContainerAppsAPIClient  # noqa: PLC0415
        from azure.monitor.querymetrics import MetricsClient  # noqa: PLC0415

        cred = get_azure_credential()
        apps_client = ContainerAppsAPIClient(cred, config.AZURE_SUBSCRIPTION_ID)
        metrics_client = MetricsClient("https://management.azure.com", cred)

        apps = list(
            apps_client.container_apps.list_by_resource_group(
                config.AZURE_CONTAINER_APPS_RESOURCE_GROUP
            )
        )

        results = []
        for app in apps:
            resource_id = app.id
            try:
                response = metrics_client.query_resource(  # type: ignore[attr-defined]
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
