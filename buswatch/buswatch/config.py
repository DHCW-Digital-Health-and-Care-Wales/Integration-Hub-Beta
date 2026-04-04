"""Runtime configuration for BusWatch."""

from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_CONNECTION_STRING = (
    "Endpoint=sb://localhost;"
    "SharedAccessKeyName=RootManageSharedAccessKey;"
    "SharedAccessKey=SAS_KEY_VALUE;"
    "UseDevelopmentEmulator=true;"
)


@dataclass(frozen=True)
class Settings:
    """Application settings sourced from environment variables."""

    servicebus_connection_string: str
    queue_names: list[str]
    peek_count: int
    detail_search_limit: int



def _parse_queue_names(raw_value: str) -> list[str]:
    """Parse comma-separated queue names from an environment variable."""
    return [name.strip() for name in raw_value.split(",") if name.strip()]



def get_settings() -> Settings:
    """Return settings used by the web app."""
    queue_names_raw = os.getenv("BUSWATCH_QUEUE_NAMES", "")
    queue_names = _parse_queue_names(queue_names_raw)

    peek_count = int(os.getenv("BUSWATCH_PEEK_COUNT", "25"))
    detail_search_limit = int(os.getenv("BUSWATCH_DETAIL_SEARCH_LIMIT", "250"))

    return Settings(
        servicebus_connection_string=os.getenv("SERVICEBUS_CONNECTION_STRING", DEFAULT_CONNECTION_STRING),
        queue_names=queue_names,
        peek_count=peek_count,
        detail_search_limit=detail_search_limit,
    )
