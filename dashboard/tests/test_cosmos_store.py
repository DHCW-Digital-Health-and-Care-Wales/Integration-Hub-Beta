"""Unit tests for the Cosmos DB persistence layer (dashboard.services.cosmos_store).

These tests mock the Cosmos SDK entirely — no emulator or live account is required.
They cover:
  - is_configured()          : endpoint-driven activation
  - get_document()           : hit / miss / not-configured / error paths and field stripping
  - upsert_document()        : payload shaping (id/pk injection) and no-op when unconfigured
  - create_document()        : create-only writes and duplicate handling
  - client auth selection    : key-based vs RBAC credential, and SSL verification toggle
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from azure.core.exceptions import ServiceRequestError
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
            "type": "alarm_config",
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

    def test_returns_none_when_cosmos_is_unreachable(self) -> None:
        """A connection-level failure (not an HTTP error response) must degrade the same way."""
        container = MagicMock()
        container.read_item.side_effect = ServiceRequestError(message="connection refused")
        with patch.object(cosmos_store, "_get_container", return_value=container):
            assert cosmos_store.get_document("alarm1", "config") is None


# ---------------------------------------------------------------------------
# query_documents
# ---------------------------------------------------------------------------


class TestQueryDocuments:
    def test_returns_empty_when_not_configured(self) -> None:
        with patch.object(cosmos_store, "_get_container", return_value=None):
            assert cosmos_store.query_documents("network-test") == []

    def test_strips_system_and_routing_fields_from_each_item(self) -> None:
        container = MagicMock()
        container.query_items.return_value = [
            {"id": "history:a:1", "pk": "network-test", "_rid": "abc", "host": "a", "port": 1, "samples": []},
            {"id": "history:b:2", "pk": "network-test", "_rid": "def", "host": "b", "port": 2, "samples": []},
        ]
        with patch.object(cosmos_store, "_get_container", return_value=container):
            result = cosmos_store.query_documents("network-test")

        assert result == [
            {"host": "a", "port": 1, "samples": []},
            {"host": "b", "port": 2, "samples": []},
        ]
        container.query_items.assert_called_once_with(
            query="SELECT * FROM c WHERE c.pk = @pk",
            parameters=[{"name": "@pk", "value": "network-test"}],
            partition_key="network-test",
        )

    def test_returns_empty_on_http_error(self) -> None:
        container = MagicMock()
        container.query_items.side_effect = CosmosHttpResponseError(message="boom")
        with patch.object(cosmos_store, "_get_container", return_value=container):
            assert cosmos_store.query_documents("network-test") == []


# ---------------------------------------------------------------------------
# upsert_document
# ---------------------------------------------------------------------------


class TestUpsertDocument:
    def test_injects_id_and_pk(self) -> None:
        container = MagicMock()
        with patch.object(cosmos_store, "_get_container", return_value=container):
            result = cosmos_store.upsert_document(
                "alarm2", "state", {"rules": {"r1": {"last_alarm_at": "2026-01-01T00:00:00"}}}
            )

        assert result is True
        container.upsert_item.assert_called_once_with(
            body={"rules": {"r1": {"last_alarm_at": "2026-01-01T00:00:00"}}, "id": "state", "pk": "alarm2"}
        )

    def test_overrides_reserved_keys_in_payload(self) -> None:
        """Any stray id/pk/type in the payload is replaced by the routing arguments."""
        container = MagicMock()
        with patch.object(cosmos_store, "_get_container", return_value=container):
            cosmos_store.upsert_document(
                "alarm3", "config", {"id": "hacked", "pk": "hacked", "type": "hacked", "rules": {}}
            )

        container.upsert_item.assert_called_once_with(body={"rules": {}, "id": "config", "pk": "alarm3"})

    def test_stamps_type_discriminator_when_supplied(self) -> None:
        """A supplied doc_type is written as a storage-managed ``type`` field."""
        container = MagicMock()
        with patch.object(cosmos_store, "_get_container", return_value=container):
            cosmos_store.upsert_document("alarm1", "config", {"rules": {}}, doc_type="alarm_config")

        container.upsert_item.assert_called_once_with(
            body={"rules": {}, "id": "config", "pk": "alarm1", "type": "alarm_config"}
        )

    def test_noop_when_container_unavailable(self) -> None:
        with patch.object(cosmos_store, "_get_container", return_value=None):
            # Not configured: no warning is warranted, so this counts as success.
            assert cosmos_store.upsert_document("alarm1", "config", {"rules": {}}) is True

    def test_returns_false_when_container_unavailable_but_configured(self) -> None:
        with (
            patch.object(cosmos_store, "_get_container", return_value=None),
            patch.object(cosmos_store, "is_configured", return_value=True),
        ):
            assert cosmos_store.upsert_document("alarm1", "config", {"rules": {}}) is False

    def test_swallows_http_error(self) -> None:
        container = MagicMock()
        container.upsert_item.side_effect = CosmosHttpResponseError(message="boom")
        with patch.object(cosmos_store, "_get_container", return_value=container):
            # Should log and return False without raising.
            assert cosmos_store.upsert_document("alarm1", "config", {"rules": {}}) is False

    def test_swallows_connectivity_error(self) -> None:
        container = MagicMock()
        container.upsert_item.side_effect = ServiceRequestError(message="connection refused")
        with patch.object(cosmos_store, "_get_container", return_value=container):
            # Should log and return False without raising.
            assert cosmos_store.upsert_document("alarm1", "config", {"rules": {}}) is False


# ---------------------------------------------------------------------------
# create_document
# ---------------------------------------------------------------------------


class TestCreateDocument:
    def test_injects_id_and_pk(self) -> None:
        container = MagicMock()
        with patch.object(cosmos_store, "_get_container", return_value=container):
            result = cosmos_store.create_document("alarm2", "state", {"rules": {"r1": "value"}})

        assert result is True
        container.create_item.assert_called_once_with(body={"rules": {"r1": "value"}, "id": "state", "pk": "alarm2"})

    def test_stamps_type_discriminator_when_supplied(self) -> None:
        container = MagicMock()
        with patch.object(cosmos_store, "_get_container", return_value=container):
            cosmos_store.create_document("alarm1", "config", {"rules": {}}, doc_type="alarm_config")

        container.create_item.assert_called_once_with(
            body={"rules": {}, "id": "config", "pk": "alarm1", "type": "alarm_config"}
        )

    def test_noop_when_container_unavailable(self) -> None:
        with patch.object(cosmos_store, "_get_container", return_value=None):
            assert cosmos_store.create_document("alarm1", "config", {"rules": {}}) is True

    def test_returns_false_when_container_unavailable_but_configured(self) -> None:
        with (
            patch.object(cosmos_store, "_get_container", return_value=None),
            patch.object(cosmos_store, "is_configured", return_value=True),
        ):
            assert cosmos_store.create_document("alarm1", "config", {"rules": {}}) is False

    def test_raises_duplicate_conflict(self) -> None:
        container = MagicMock()
        container.create_item.side_effect = CosmosResourceExistsError(message="duplicate")
        with (
            patch.object(cosmos_store, "_get_container", return_value=container),
            pytest.raises(CosmosResourceExistsError),
        ):
            cosmos_store.create_document("alarm1", "config", {"rules": {}})

    def test_swallows_other_http_errors(self) -> None:
        container = MagicMock()
        container.create_item.side_effect = CosmosHttpResponseError(message="boom")
        with patch.object(cosmos_store, "_get_container", return_value=container):
            assert cosmos_store.create_document("alarm1", "config", {"rules": {}}) is False


# ---------------------------------------------------------------------------
# delete_document
# ---------------------------------------------------------------------------


class TestDeleteDocument:
    def test_deletes_by_pk_and_id(self) -> None:
        container = MagicMock()
        with patch.object(cosmos_store, "_get_container", return_value=container):
            result = cosmos_store.delete_document("network-test", "history:a:1")

        assert result is True
        container.delete_item.assert_called_once_with(item="history:a:1", partition_key="network-test")

    def test_noop_when_container_unavailable(self) -> None:
        with patch.object(cosmos_store, "_get_container", return_value=None):
            assert cosmos_store.delete_document("network-test", "history:a:1") is True

    def test_noop_when_document_already_missing(self) -> None:
        container = MagicMock()
        container.delete_item.side_effect = CosmosResourceNotFoundError(message="missing")
        with patch.object(cosmos_store, "_get_container", return_value=container):
            assert cosmos_store.delete_document("network-test", "history:a:1") is True

    def test_swallows_http_error(self) -> None:
        container = MagicMock()
        container.delete_item.side_effect = CosmosHttpResponseError(message="boom")
        with patch.object(cosmos_store, "_get_container", return_value=container):
            assert cosmos_store.delete_document("network-test", "history:a:1") is False


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
            patch.object(cosmos_store.config, "COSMOS_CONTAINER", "dashboard"),
        ):
            result = cosmos_store._get_container()

        assert result is existing_container
        database.get_container_client.assert_called_once_with("dashboard")

    def test_returns_none_on_other_http_error(self) -> None:
        database = MagicMock(name="database")
        database.create_container_if_not_exists.side_effect = CosmosHttpResponseError(message="boom")

        client = MagicMock(name="client")
        client.create_database_if_not_exists.return_value = database

        with (
            patch.object(cosmos_store, "_get_client", return_value=client),
            patch.object(cosmos_store.config, "COSMOS_KEY", "the-key"),
            patch.object(cosmos_store.config, "COSMOS_DATABASE", "db"),
            patch.object(cosmos_store.config, "COSMOS_CONTAINER", "dashboard"),
        ):
            assert cosmos_store._get_container() is None

    def test_returns_none_when_client_unavailable(self) -> None:
        with patch.object(cosmos_store, "_get_client", return_value=None):
            assert cosmos_store._get_container() is None
