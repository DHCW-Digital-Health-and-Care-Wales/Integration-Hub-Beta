"""
Trace drilldown service — queries Log Analytics for all telemetry
associated with a given App Insights operation_id.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from azure.monitor.query import LogsQueryStatus

from dashboard import config
from dashboard.services.azure_monitor import _get_logs_client

log = logging.getLogger(__name__)

_OPERATION_ID_RE = re.compile(r"^[a-zA-Z0-9\-_|]+$")


def _empty() -> dict:
    return {
        "spans": [],
        "exceptions": [],
        "logs": [],
        "duration_ms": 0,
        "start_time": "",
        "ok": False,
    }


def get_trace(operation_id: str) -> dict:
    """
    Query Log Analytics for all telemetry associated with the given operation_id.
    Returns a dict with keys: spans, exceptions, logs, duration_ms, start_time, ok.
    Falls back gracefully (returns empty structure) on any error.
    """
    if not _OPERATION_ID_RE.match(operation_id):
        log.warning("Invalid operation_id rejected: %r", operation_id)
        return _empty()

    # Reject the all-zeros null trace ID — it matches everything and returns GB of data
    if re.match(r"^0+$", operation_id):
        log.warning("Null operation_id rejected: %r", operation_id)
        return _empty()

    if not config.AZURE_LOG_ANALYTICS_WORKSPACE_ID:
        log.warning("Log Analytics workspace not configured — returning empty trace")
        return _empty()

    query = f"""union
  (AppRequests    | extend itemType = "AppRequests"),
  (AppDependencies | extend itemType = "AppDependencies"),
  (AppTraces      | extend itemType = "AppTraces"),
  (AppExceptions  | extend itemType = "AppExceptions")
| where OperationId == "{operation_id}"
| project
    TimeGenerated,
    itemType,
    name = coalesce(Name, Message, ExceptionType),
    duration = DurationMs,
    success = Success,
    resultCode = ResultCode,
    target = Target,
    parentId = ParentId,
    id = Id,
    appName = AppRoleName,
    severityLevel = SeverityLevel,
    message = coalesce(OuterMessage, Message, "")
| order by TimeGenerated asc
| take 500"""

    try:
        client = _get_logs_client()
        response = client.query_workspace(
            workspace_id=config.AZURE_LOG_ANALYTICS_WORKSPACE_ID,
            query=query,
            timespan=timedelta(hours=24),
        )
    except Exception as exc:
        log.error("Failed to fetch trace %s: %s", operation_id, exc)
        return _empty()

    if response.status in (LogsQueryStatus.FAILURE, LogsQueryStatus.PARTIAL):
        log.warning("Log Analytics trace query returned non-success status (%s): %s", response.status, response.partial_error)
        return _empty()

    tables = response.tables
    spans: list[dict] = []
    exceptions: list[dict] = []
    logs: list[dict] = []
    timestamps: list[Any] = []

    for table in tables:
        for row in table.rows:
            r = dict(zip(table.columns, row))
            ts = r.get("TimeGenerated")
            if ts is not None:
                timestamps.append(ts)
            item_type = str(r.get("itemType", ""))

            if item_type in ("AppRequests", "AppDependencies"):
                spans.append(
                    {
                        "name": str(r.get("name", "") or ""),
                        "duration": r.get("duration"),
                        "success": r.get("success"),
                        "target": str(r.get("target", "") or ""),
                        "app_name": str(r.get("appName", "") or ""),
                        "start_time": str(ts) if ts is not None else "",
                        "parent_id": str(r.get("parentId", "") or ""),
                    }
                )
            elif item_type == "AppExceptions":
                exceptions.append(
                    {
                        "name": str(r.get("name", "") or ""),
                        "message": str(r.get("message", "") or ""),
                        "app_name": str(r.get("appName", "") or ""),
                        "timestamp": str(ts) if ts is not None else "",
                    }
                )
            elif item_type == "AppTraces":
                logs.append(
                    {
                        "message": str(r.get("message", "") or ""),
                        "app_name": str(r.get("appName", "") or ""),
                        "severity": r.get("severityLevel"),
                        "timestamp": str(ts) if ts is not None else "",
                    }
                )

    duration_ms: float = 0.0
    start_time: str = ""
    if timestamps:
        try:
            dt_list: list[datetime] = []
            for t in timestamps:
                if isinstance(t, datetime):
                    dt_aware = t if t.tzinfo else t.replace(tzinfo=timezone.utc)
                    dt_list.append(dt_aware)
                else:
                    dt_list.append(datetime.fromisoformat(str(t).replace("Z", "+00:00")))
            dt_list.sort()
            start_time = dt_list[0].isoformat()
            if len(dt_list) > 1:
                duration_ms = (dt_list[-1] - dt_list[0]).total_seconds() * 1000
        except Exception as exc:
            log.warning("Could not compute trace duration: %s", exc)
            start_time = str(timestamps[0])

    return {
        "spans": spans,
        "exceptions": exceptions,
        "logs": logs,
        "duration_ms": round(duration_ms, 1),
        "start_time": start_time,
        "ok": len(spans) > 0,
    }
