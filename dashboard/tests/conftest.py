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

from dashboard.services import cosmos_store


@pytest.fixture(autouse=True)
def _disable_cosmos() -> Generator[None, None, None]:
    """Disable Cosmos persistence for every test and reset the cached client."""
    cosmos_store._reset_client_for_tests()
    with patch.object(cosmos_store.config, "COSMOS_ENDPOINT", ""):
        yield
    cosmos_store._reset_client_for_tests()
