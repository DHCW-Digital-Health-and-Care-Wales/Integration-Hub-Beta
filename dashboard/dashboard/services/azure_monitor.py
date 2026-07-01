"""
Azure Monitor / Log Analytics queries for the Integration Hub.
"""

from __future__ import annotations

import json
import logging
import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from azure.mgmt.appcontainers import ContainerAppsAPIClient  # noqa: PLC0415
from azure.monitor.query import LogsQueryClient, LogsQueryStatus

from dashboard import config
from dashboard.services.credentials import get_azure_credential

log = logging.getLogger(__name__)

# Azure Container App naming rules: lowercase letters, digits, hyphens;
# 1–32 characters; must start and end with a letter or digit.
_CONTAINER_APP_NAME_RE = re.compile(r"[a-z0-9]([a-z0-9\-]{0,30}[a-z0-9])?$")


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


def get_retry_delay_metrics_by_flow(hours: int = 1, min_delay_seconds: float = 60.0) -> list[dict]:
    """Return latest retry delay metric per workflow from AppMetrics.

    The ``retry_delay_seconds`` metric is emitted by the shared message bus
    receiver when exponential backoff is scheduled after a failed processing
    attempt.
    """
    if not _credentials_configured():
        log.warning("Log Analytics workspace not configured — returning empty retry-delay list")
        return []

    # Guard against invalid runtime values being interpolated into KQL.
    try:
        query_hours = int(hours)
    except (TypeError, ValueError):
        query_hours = 1
    if query_hours < 1:
        query_hours = 1

    try:
        query_min_delay = float(min_delay_seconds)
    except (TypeError, ValueError):
        query_min_delay = 60.0
    if not math.isfinite(query_min_delay) or query_min_delay < 0:
        query_min_delay = 60.0

    query = f"""
    AppMetrics
    | where TimeGenerated > ago({query_hours}h)
    | where Name == "retry_delay_seconds"
    | extend workflow_id = tostring(Properties["workflow_id"])
    | extend microservice_id = tostring(Properties["microservice_id"])
    | extend queue = tostring(Properties["queue"])
    | extend attempt = tostring(Properties["attempt"])
    | where isnotempty(workflow_id)
    | summarize arg_max(TimeGenerated, Sum, microservice_id, queue, attempt) by workflow_id
    | project workflow_id, timestamp=TimeGenerated, delay_seconds=todouble(Sum), microservice_id, queue, attempt
    | where delay_seconds > {query_min_delay}
    | order by workflow_id asc
    """
    try:
        client = _get_logs_client()
        response = client.query_workspace(
            workspace_id=config.AZURE_LOG_ANALYTICS_WORKSPACE_ID,
            query=query,
            timespan=timedelta(hours=query_hours),
        )
        if response.status != LogsQueryStatus.SUCCESS:
            log.error("Retry-delay query failed: %s", response.partial_error)
            return []

        rows: list[dict] = []
        for table in response.tables:
            for row in table.rows:
                row_dict = dict(zip(table.columns, row))
                attempt_value = row_dict.get("attempt")
                attempt_int: int | None
                try:
                    attempt_int = (
                        int(attempt_value) if attempt_value not in (None, "")
                        and attempt_value is not None else None
                    )
                except (TypeError, ValueError):
                    attempt_int = None

                delay_raw = row_dict.get("delay_seconds")
                delay_float: float | None
                try:
                    delay_float = float(delay_raw) if delay_raw is not None else None
                except (TypeError, ValueError):
                    delay_float = None

                rows.append(
                    {
                        "workflow_id": str(row_dict.get("workflow_id") or ""),
                        "timestamp": str(row_dict.get("timestamp") or ""),
                        "delay_seconds": delay_float,
                        "microservice_id": str(row_dict.get("microservice_id") or ""),
                        "queue": str(row_dict.get("queue") or ""),
                        "attempt": attempt_int,
                    }
                )
        return [
            row
            for row in rows
            if row.get("delay_seconds") is not None and float(row["delay_seconds"]) > query_min_delay
        ]
    except Exception as exc:
        log.error("Failed to fetch retry delay metrics: %s", exc)
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
        cred = get_azure_credential()
        # Use the per-resource metrics REST endpoint — requires only Microsoft.Insights/metrics/read
        # on each resource, not the subscription-level metrics:getBatch permission needed by the
        # batch SDK (MetricsClient.query_resources).
        token = cred.get_token("https://management.azure.com/.default").token
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

        apps_client = ContainerAppsAPIClient(cred, config.AZURE_SUBSCRIPTION_ID)
        apps = list(apps_client.container_apps.list_by_resource_group(config.AZURE_CONTAINER_APPS_RESOURCE_GROUP))

        now = datetime.now(timezone.utc)
        start = (now - timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%SZ")
        end = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        results = []
        for app in apps:
            try:
                # Build the query string manually — requests would percent-encode commas in
                # metricnames and slashes in timespan, causing a 400 from Azure Monitor.
                # Correct metric names per Microsoft.App/containerapps:
                #   CpuPercentage, WorkingSetBytes, Replicas
                query = (
                    "api-version=2018-01-01"
                    "&metricnames=CpuPercentage,WorkingSetBytes,Replicas"
                    f"&timespan={start}/{end}"
                    "&interval=PT5M"
                    "&aggregation=Average"
                    "&metricnamespace=microsoft.app/containerapps"
                )
                url = f"https://management.azure.com{app.id}/providers/microsoft.insights/metrics?{query}"
                resp = requests.get(url, headers=headers, timeout=10)
                resp.raise_for_status()
                data = resp.json()

                metrics: dict = {}
                for m in data.get("value", []):
                    metric_name = m.get("name", {}).get("value", "")
                    for ts in m.get("timeseries", []):
                        for dp in reversed(ts.get("data", [])):
                            val = dp.get("average")
                            if val is not None:
                                metrics[metric_name] = round(val, 2)
                                break

                results.append(
                    {
                        "name": app.name,
                        "location": app.location,
                        "cpu_usage": metrics.get("CpuPercentage", 0),
                        "memory_bytes": metrics.get("WorkingSetBytes", 0),
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


def get_container_app_metric_history(app_name: str, hours: int = 1) -> dict:
    """
    Query Azure Monitor for CPU and memory time-series for a single Container App.

    Returns a dict::

        {
            "name": "<app_name>",
            "timestamps": ["2024-01-01T00:00:00Z", ...],
            "cpu":        [12.3, None, 14.1, ...],   # CpuPercentage (%); None where data is absent
            "memory_mb":  [128.4, 130.2, ...],       # WorkingSetBytes converted to MiB; None where absent
        }

    Falls back to a dict with empty lists on any error.
    """
    empty = {"name": app_name, "timestamps": [], "cpu": [], "memory_mb": []}

    if not all(
        [
            config.AZURE_SUBSCRIPTION_ID,
            config.AZURE_CONTAINER_APPS_RESOURCE_GROUP,
        ]
    ):
        log.warning("Container Apps resource configuration missing")
        return empty

    # Validate the app name to avoid URL injection — Container App names follow
    # Azure naming rules (see _CONTAINER_APP_NAME_RE).
    if not _CONTAINER_APP_NAME_RE.fullmatch(app_name):
        log.warning("Invalid container app name: %r", app_name)
        return empty

    # Choose an appropriate aggregation interval based on the requested window.
    if hours <= 1:
        interval = "PT1M"
    elif hours <= 6:
        interval = "PT5M"
    elif hours <= 24:
        interval = "PT15M"
    else:
        interval = "PT1H"

    try:
        import requests  # noqa: PLC0415

        cred = get_azure_credential()
        token = cred.get_token("https://management.azure.com/.default").token
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

        now = datetime.now(timezone.utc)
        start = (now - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
        end = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        resource_id = (
            f"/subscriptions/{config.AZURE_SUBSCRIPTION_ID}"
            f"/resourceGroups/{config.AZURE_CONTAINER_APPS_RESOURCE_GROUP}"
            f"/providers/Microsoft.App/containerApps/{app_name}"
        )
        query = (
            "api-version=2018-01-01"
            "&metricnames=CpuPercentage,WorkingSetBytes"
            f"&timespan={start}/{end}"
            f"&interval={interval}"
            "&aggregation=Average"
            "&metricnamespace=microsoft.app/containerapps"
        )
        url = f"https://management.azure.com{resource_id}/providers/microsoft.insights/metrics?{query}"
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        # Build a unified timestamp axis from the CPU series (both series share
        # the same interval so timestamps line up).
        cpu_points: dict[str, float] = {}
        mem_points: dict[str, float] = {}
        for m in data.get("value", []):
            metric_name = m.get("name", {}).get("value", "")
            for ts in m.get("timeseries", []):
                for dp in ts.get("data", []):
                    t = dp.get("timeStamp")
                    val = dp.get("average")
                    if t is None or val is None:
                        continue
                    if metric_name == "CpuPercentage":
                        cpu_points[t] = round(float(val), 2)
                    elif metric_name == "WorkingSetBytes":
                        mem_points[t] = round(float(val) / 1048576, 2)

        timestamps = sorted(set(cpu_points) | set(mem_points))
        return {
            "name": app_name,
            "timestamps": timestamps,
            "cpu": [cpu_points.get(t) for t in timestamps],
            "memory_mb": [mem_points.get(t) for t in timestamps],
        }
    except Exception as exc:
        log.error("Failed to fetch metric history for %s: %s", app_name, exc)
        return empty
