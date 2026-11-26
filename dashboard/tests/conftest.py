"""Shared pytest fixtures for the dashboard test suite.

Unit tests must be hermetic — they must never reach a live Azure Cosmos account or
the local emulator. Because ``dashboard/.env`` configures ``COSMOS_ENDPOINT`` for local
development, an autouse fixture disables Cosmos persistence for every test by default so
alarm config/state reads simply return empty (mirroring the previous "missing JSON file"
behaviour). Tests that specifically exercise :mod:`dashboard.services.cosmos_store` opt
back in by patching the endpoint explicitly within the test.
"""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import patch

import pytest

from dashboard.services import (
    alarm_base,
    alarm_pauses,
    arm,
    azure_monitor,
    cache,
    contacts_store,
    cosmos_store,
    email_service,
    service_bus,
)


def _reset_caches() -> None:
    cosmos_store._reset_client_for_tests()
    service_bus._reset_client_for_tests()
    azure_monitor._reset_clients_for_tests()
    arm._reset_client_for_tests()
    email_service._reset_clients_for_tests()
    cache.reset_for_tests()
    alarm_base.invalidate_config_cache()
    alarm_pauses.invalidate_pauses_cache()
    contacts_store.invalidate_contacts_cache()


@pytest.fixture(autouse=True)
def _disable_cosmos() -> Generator[None, None, None]:
    """Keep tests hermetic regardless of local ``dashboard/.env`` settings."""
    _reset_caches()
    with (
        patch.object(cosmos_store.config, "COSMOS_ENDPOINT", ""),
        patch.object(cosmos_store.config, "DEMO_MODE", False),
    ):
        yield
    _reset_caches()
