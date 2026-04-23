"""
Azure Service Bus queue metrics via azure-mgmt-servicebus.
"""
from __future__ import annotations

import logging

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
