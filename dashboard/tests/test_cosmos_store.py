"""Unit tests for the Cosmos DB persistence layer (dashboard.services.cosmos_store).

These tests mock the Cosmos SDK entirely — no emulator or live account is required.
They cover:
  - is_configured()          : endpoint-driven activation
  - get_document()           : hit / miss / not-configured / error paths and field stripping
  - upsert_document()        : payload shaping (id/pk injection) and no-op when unconfigured
  - client auth selection    : key-based vs RBAC credential, and SSL verification toggle
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from azure.cosmos.exceptions import (
    CosmosHttpResponseError,
    CosmosResourceExistsError,
    CosmosResourceNotFoundError,
)

from dashboard.services import cosmos_store


@pytest.fixture(autouse=True)
def _reset_client() -> Any:
    """Ensure each test starts and ends with a clean singleton client."""
    cosmos_store._reset_client_for_tests()
    yield
    cosmos_store._reset_client_for_tests()


# ---------------------------------------------------------------------------
# is_configured
# ---------------------------------------------------------------------------


class TestIsConfigured:
    def test_true_when_endpoint_set(self) -> None:
        with patch.object(cosmos_store.config, "COSMOS_ENDPOINT", "https://localhost:8081"):
            assert cosmos_store.is_configured() is True

    def test_false_when_endpoint_empty(self) -> None:
        with patch.object(cosmos_store.config, "COSMOS_ENDPOINT", ""):
            assert cosmos_store.is_configured() is False


# ---------------------------------------------------------------------------
# get_document
# ---------------------------------------------------------------------------


class TestGetDocument:
    def test_returns_none_when_not_configured(self) -> None:
        with patch.object(cosmos_store.config, "COSMOS_ENDPOINT", ""):
            assert cosmos_store.get_document("alarm1", "config") is None

    def test_strips_system_and_routing_fields(self) -> None:
        container = MagicMock()
        container.read_item.return_value = {
            "id": "config",
            "pk": "alarm1",
            "_rid": "abc",
            "_etag": "xyz",
            "_ts": 123,
            "rules": {"r1": {"alarm_enabled": True}},
        }
        with patch.object(cosmos_store, "_get_container", return_value=container):
            result = cosmos_store.get_document("alarm1", "config")

        assert result == {"rules": {"r1": {"alarm_enabled": True}}}
        container.read_item.assert_called_once_with(item="config", partition_key="alarm1")

    def test_returns_none_on_missing_document(self) -> None:
        container = MagicMock()
        container.read_item.side_effect = CosmosResourceNotFoundError(message="missing")
        with patch.object(cosmos_store, "_get_container", return_value=container):
            assert cosmos_store.get_document("alarm1", "config") is None

    def test_returns_none_on_http_error(self) -> None:
        container = MagicMock()
        container.read_item.side_effect = CosmosHttpResponseError(message="boom")
        with patch.object(cosmos_store, "_get_container", return_value=container):
            assert cosmos_store.get_document("alarm1", "config") is None


# ---------------------------------------------------------------------------
# upsert_document
# ---------------------------------------------------------------------------


class TestUpsertDocument:
    def test_injects_id_and_pk(self) -> None:
        container = MagicMock()
        with patch.object(cosmos_store, "_get_container", return_value=container):
            cosmos_store.upsert_document("alarm2", "state", {"rules": {"r1": {"last_alarm_at": "2026-01-01T00:00:00"}}})

        container.upsert_item.assert_called_once_with(
            body={"rules": {"r1": {"last_alarm_at": "2026-01-01T00:00:00"}}, "id": "state", "pk": "alarm2"}
        )

    def test_overrides_reserved_keys_in_payload(self) -> None:
        """Any stray id/pk in the payload is replaced by the routing arguments."""
        container = MagicMock()
        with patch.object(cosmos_store, "_get_container", return_value=container):
            cosmos_store.upsert_document("alarm3", "config", {"id": "hacked", "pk": "hacked", "rules": {}})

        container.upsert_item.assert_called_once_with(body={"rules": {}, "id": "config", "pk": "alarm3"})

    def test_noop_when_container_unavailable(self) -> None:
        with patch.object(cosmos_store, "_get_container", return_value=None):
            # Should not raise.
            cosmos_store.upsert_document("alarm1", "config", {"rules": {}})

    def test_swallows_http_error(self) -> None:
        container = MagicMock()
        container.upsert_item.side_effect = CosmosHttpResponseError(message="boom")
        with patch.object(cosmos_store, "_get_container", return_value=container):
            # Should log and return without raising.
            cosmos_store.upsert_document("alarm1", "config", {"rules": {}})


# ---------------------------------------------------------------------------
# _get_client — auth selection
# ---------------------------------------------------------------------------


class TestGetClient:
    def test_returns_none_when_not_configured(self) -> None:
        with patch.object(cosmos_store.config, "COSMOS_ENDPOINT", ""):
            assert cosmos_store._get_client() is None

    def test_uses_key_when_set(self) -> None:
        with (
            patch.object(cosmos_store.config, "COSMOS_ENDPOINT", "https://localhost:8081"),
            patch.object(cosmos_store.config, "COSMOS_KEY", "the-key"),
            patch.object(cosmos_store.config, "COSMOS_DISABLE_SSL_VERIFY", True),
            patch("dashboard.services.cosmos_store.CosmosClient") as client_cls,
        ):
            cosmos_store._get_client()

        client_cls.assert_called_once_with(
            "https://localhost:8081", credential="the-key", connection_verify=False, enable_endpoint_discovery=False
        )

    def test_uses_azure_credential_when_key_absent(self) -> None:
        sentinel = object()
        with (
            patch.object(cosmos_store.config, "COSMOS_ENDPOINT", "https://acct.documents.azure.com"),
            patch.object(cosmos_store.config, "COSMOS_KEY", ""),
            patch.object(cosmos_store.config, "COSMOS_DISABLE_SSL_VERIFY", False),
            patch("dashboard.services.cosmos_store.get_azure_credential", return_value=sentinel),
            patch("dashboard.services.cosmos_store.CosmosClient") as client_cls,
        ):
            cosmos_store._get_client()

        client_cls.assert_called_once_with("https://acct.documents.azure.com", credential=sentinel)

    def test_client_is_cached_singleton(self) -> None:
        with (
            patch.object(cosmos_store.config, "COSMOS_ENDPOINT", "https://localhost:8081"),
            patch.object(cosmos_store.config, "COSMOS_KEY", "the-key"),
            patch.object(cosmos_store.config, "COSMOS_DISABLE_SSL_VERIFY", False),
            patch("dashboard.services.cosmos_store.CosmosClient") as client_cls,
        ):
            first = cosmos_store._get_client()
            second = cosmos_store._get_client()

        assert first is second
        client_cls.assert_called_once()


# ---------------------------------------------------------------------------
# _get_container — database/container resolution
# ---------------------------------------------------------------------------


class TestGetContainer:
    def test_falls_back_to_existing_container_on_conflict(self) -> None:
        """A 409 from a concurrent worker's create must resolve to the existing container.

        Two gunicorn workers race to create the container on a fresh emulator: both read
        a 404, both call create, and the loser receives a 409 Conflict. The loser must
        return the already-created container rather than degrading to ``None``.
        """
        existing_container = MagicMock(name="existing_container")
        database = MagicMock(name="database")
        database.create_container_if_not_exists.side_effect = CosmosResourceExistsError(message="already exists")
        database.get_container_client.return_value = existing_container

        client = MagicMock(name="client")
        client.create_database_if_not_exists.return_value = database
        client.get_database_client.return_value = database

        with (
            patch.object(cosmos_store, "_get_client", return_value=client),
            patch.object(cosmos_store.config, "COSMOS_KEY", "the-key"),
            patch.object(cosmos_store.config, "COSMOS_DATABASE", "db"),
            patch.object(cosmos_store.config, "COSMOS_CONTAINER", "alarms"),
        ):
            result = cosmos_store._get_alarm_container()

        assert result is existing_container
        database.get_container_client.assert_called_once_with("alarms")

    def test_returns_none_on_other_http_error(self) -> None:
        database = MagicMock(name="database")
        database.create_container_if_not_exists.side_effect = CosmosHttpResponseError(message="boom")

        client = MagicMock(name="client")
        client.create_database_if_not_exists.return_value = database

        with (
            patch.object(cosmos_store, "_get_client", return_value=client),
            patch.object(cosmos_store.config, "COSMOS_KEY", "the-key"),
            patch.object(cosmos_store.config, "COSMOS_DATABASE", "db"),
            patch.object(cosmos_store.config, "COSMOS_CONTAINER", "alarms"),
        ):
            assert cosmos_store._get_alarm_container() is None

    def test_returns_none_when_client_unavailable(self) -> None:
        with patch.object(cosmos_store, "_get_client", return_value=None):
            assert cosmos_store._get_alarm_container() is None

