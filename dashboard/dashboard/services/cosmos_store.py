"""Azure Cosmos DB persistence layer for dashboard alarm config and state.

This module replaces the previous JSON-file persistence used by the alarm services.
Each alarm namespace (``alarm1``/``alarm2``/``alarm3``) stores two small documents —
``config`` and ``state`` — in a single Cosmos container partitioned on ``/pk``.

Design notes:
  * A single :class:`~azure.cosmos.CosmosClient` is created lazily and reused as a
    process-wide singleton (SDK best practice — the client manages its own connection
    pool and should not be recreated per request).
  * Authentication is dual-mode:
      - When ``COSMOS_KEY`` is set (the local emulator, or key-based cloud access) the
        account key is used and the database/container are created on demand.
      - When ``COSMOS_KEY`` is empty the shared Azure credential (Managed Identity /
        service principal) is used for data-plane RBAC. In this mode the database and
        container are assumed to already exist (provisioned via Terraform), because
        creating them requires management-plane permissions the data-plane role lacks.
  * When ``COSMOS_ENDPOINT`` is not configured every operation is a no-op: reads return
    ``None`` and writes are skipped. This keeps the dashboard's graceful-degradation
    behaviour (alarm pages still render with empty config).

The partition key is the alarm namespace (low cardinality but the workload is tiny —
at most a handful of documents — so this keeps every read a single-partition point read).
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from azure.cosmos import CosmosClient, PartitionKey
from azure.cosmos.exceptions import (
    CosmosHttpResponseError,
    CosmosResourceExistsError,
    CosmosResourceNotFoundError,
)

from dashboard import config
from dashboard.services.credentials import get_azure_credential

log = logging.getLogger(__name__)

# Cosmos reserves any property whose name starts with ``_`` (``_rid``, ``_etag`` …)
# plus the ``id``/``pk`` routing fields. These are stripped from documents on read so
# callers get back exactly the payload they stored.
_RESERVED_KEYS = frozenset({"id", "pk"})

# Single-element mutable cache holding the process-wide client. A dict is used (rather
# than a reassigned module global) so the singleton can be updated without ``global``.
_client_cache: dict[str, CosmosClient | None] = {"client": None}
_client_lock = threading.Lock()


def is_configured() -> bool:
    """Return ``True`` when a Cosmos endpoint is configured and persistence is active."""
    return bool(config.COSMOS_ENDPOINT)


def _get_client() -> CosmosClient | None:
    """Return the process-wide singleton CosmosClient, building it on first use."""
    if not is_configured():
        return None
    if _client_cache["client"] is not None:
        return _client_cache["client"]

    with _client_lock:
        if _client_cache["client"] is not None:
            return _client_cache["client"]

        # The emulator uses a self-signed certificate; verification must be disabled
        # locally. Never disable verification against a real Cosmos account.
        client_kwargs: dict[str, Any] = {}
        if config.COSMOS_DISABLE_SSL_VERIFY:
            endpoint = config.COSMOS_ENDPOINT.lower()
            if "localhost" not in endpoint and "127.0.0.1" not in endpoint and "cosmos-emulator" not in endpoint:
                log.error(
                    "Refusing to disable Cosmos TLS verification for non-local endpoint: %s",
                    config.COSMOS_ENDPOINT,
                )
            else:
                client_kwargs["connection_verify"] = False
                # The Dockerised emulator advertises its internal container IP via endpoint
                # discovery, which the host cannot reach. Disabling discovery pins the client
                # to the configured gateway endpoint (localhost:8081).
                client_kwargs["enable_endpoint_discovery"] = False

        credential: Any = config.COSMOS_KEY or get_azure_credential()
        try:
            _client_cache["client"] = CosmosClient(config.COSMOS_ENDPOINT, credential=credential, **client_kwargs)
        except Exception as exc:  # noqa: BLE001 — surface as degraded, never crash the app
            log.error("Failed to initialise Cosmos client: %s", exc)
            return None

    return _client_cache["client"]


def _get_alarm_container() -> Any | None:
    """Return the alarm container client, creating the database/container in dev.

    When key-based auth is used (emulator / dev) the database and container are created
    on demand so a fresh emulator needs no manual setup. With RBAC auth they are assumed
    to already exist.
    """
    client = _get_client()
    if client is None:
        return None

    try:
        if config.COSMOS_KEY:
            database = client.create_database_if_not_exists(id=config.COSMOS_DATABASE)
            return database.create_container_if_not_exists(
                id=config.COSMOS_CONTAINER,
                partition_key=PartitionKey(path="/pk"),
            )
        database = client.get_database_client(config.COSMOS_DATABASE)
        return database.get_container_client(config.COSMOS_CONTAINER)
    except CosmosResourceExistsError:
        # Multiple gunicorn workers can race to create the database/container on a
        # fresh emulator: all read a 404, all attempt to create, and the losers get a
        # 409 Conflict. That simply means the resource now exists, so return the
        # existing container client rather than degrading this worker's persistence.
        database = client.get_database_client(config.COSMOS_DATABASE)
        return database.get_container_client(config.COSMOS_CONTAINER)
    except CosmosHttpResponseError as exc:
        log.error("Failed to access Cosmos container '%s': %s", config.COSMOS_CONTAINER, exc)
        return None


def get_document(pk: str, doc_id: str) -> dict | None:
    """Read a single document by partition key and id.

    Returns the stored payload (Cosmos system fields and routing keys stripped) or
    ``None`` when the document is missing, Cosmos is not configured, or a read error
    occurs. Errors are logged and swallowed so callers can fall back to defaults.
    """
    container = _get_alarm_container()
    if container is None:
        return None

    try:
        item = container.read_item(item=doc_id, partition_key=pk)
    except CosmosResourceNotFoundError:
        return None
    except CosmosHttpResponseError as exc:
        log.warning("Failed to read Cosmos document %s/%s: %s", pk, doc_id, exc)
        return None

    return {k: v for k, v in item.items() if k not in _RESERVED_KEYS and not k.startswith("_")}


def upsert_document(pk: str, doc_id: str, data: dict) -> None:
    """Create or replace a document identified by ``pk``/``doc_id``.

    The ``data`` payload is stored verbatim alongside the ``id`` and ``pk`` routing
    fields. Errors are logged and swallowed so a persistence outage never breaks a
    request — matching the previous JSON-file save behaviour.
    """
    container = _get_alarm_container()
    if container is None:
        if is_configured():
            log.error("Cannot persist Cosmos document %s/%s — container unavailable", pk, doc_id)
        return

    document = {k: v for k, v in data.items() if k not in _RESERVED_KEYS}
    document["id"] = doc_id
    document["pk"] = pk

    try:
        container.upsert_item(body=document)
    except CosmosHttpResponseError as exc:
        log.error("Failed to persist Cosmos document %s/%s: %s", pk, doc_id, exc)


def _reset_client_for_tests() -> None:
    """Clear the cached client — used by unit tests to isolate configuration changes."""
    with _client_lock:
        _client_cache["client"] = None
