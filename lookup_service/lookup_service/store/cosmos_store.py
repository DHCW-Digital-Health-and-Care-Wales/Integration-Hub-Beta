"""Cosmos DB-backed table store (async SDK).

Containers:
  * rows   (partition key /table_name): one document per row; id = encoded canonical key, so a lookup
    is a single-partition point read.
  * config (partition key /pk): one document per table (pk "table") holding the definition and stats.

Auth follows the dashboard's dual mode: COSMOS_KEY set -> key auth and the database/containers are
created if missing (local emulator); COSMOS_KEY empty -> DefaultAzureCredential (Managed Identity) and
the containers must already exist (provisioned by Terraform - data-plane roles can't create them).
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable, Iterable, Sequence
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any, TypeVar

from azure.core.exceptions import AzureError
from azure.cosmos import PartitionKey
from azure.cosmos.aio import ContainerProxy, CosmosClient
from azure.cosmos.exceptions import CosmosResourceNotFoundError
from azure.identity.aio import DefaultAzureCredential

from lookup_service.config import Settings
from lookup_service.errors import BackendUnavailableError
from lookup_service.keys import encode_row_id, key_text
from lookup_service.models import Row, TableDefinition, TableRecord, TableStats, UploadInfo
from lookup_service.store.base import ReplaceResult

logger = logging.getLogger(__name__)

CONFIG_TABLE_PK = "table"
MAX_BATCH_OPERATIONS = 100
# Cosmos caps a transactional batch request at 2 MB; leave headroom for envelope overhead.
MAX_BATCH_BYTES = 1_500_000
# Measured ~8x faster than the SDK default page size when listing a large table's ids or rows.
QUERY_PAGE_SIZE = 1000
T = TypeVar("T")

_COUNT_ROWS = "SELECT VALUE COUNT(1) FROM c"
_COUNT_ROWS_MATCHING = "SELECT VALUE COUNT(1) FROM c WHERE CONTAINS(c.key_text, @search, true)"
_PAGE_ROWS = 'SELECT c.key, c["values"] FROM c ORDER BY c.key_text OFFSET @offset LIMIT @limit'
_PAGE_ROWS_MATCHING = (
    'SELECT c.key, c["values"] FROM c WHERE CONTAINS(c.key_text, @search, true) '
    "ORDER BY c.key_text OFFSET @offset LIMIT @limit"
)


class CosmosTableStore:
    source = "cosmos"
    writable = True

    def __init__(self, settings: Settings) -> None:
        if not settings.cosmos_endpoint:
            raise ValueError("CosmosTableStore requires COSMOS_ENDPOINT")
        self._settings = settings
        self._client: CosmosClient | None = None
        self._credential: DefaultAzureCredential | None = None
        self._rows: ContainerProxy | None = None
        self._config: ContainerProxy | None = None

    async def open(self) -> None:
        settings = self._settings
        endpoint = settings.cosmos_endpoint or ""
        client_kwargs: dict[str, Any] = {}
        if settings.cosmos_disable_ssl_verify:
            # Settings.validate() has already restricted this to emulator endpoints.
            client_kwargs["connection_verify"] = False
            # The Dockerised emulator advertises an internal address via endpoint discovery; pin to the gateway.
            client_kwargs["enable_endpoint_discovery"] = False

        credential: Any
        if settings.cosmos_key:
            credential = settings.cosmos_key
        else:
            self._credential = DefaultAzureCredential()
            credential = self._credential
        self._client = CosmosClient(endpoint, credential=credential, **client_kwargs)

        try:
            if settings.cosmos_key:
                database = await self._client.create_database_if_not_exists(id=settings.cosmos_database)
                self._rows = await database.create_container_if_not_exists(
                    id=settings.rows_container, partition_key=PartitionKey(path="/table_name")
                )
                self._config = await database.create_container_if_not_exists(
                    id=settings.config_container, partition_key=PartitionKey(path="/pk")
                )
            else:
                database = self._client.get_database_client(settings.cosmos_database)
                self._rows = database.get_container_client(settings.rows_container)
                self._config = database.get_container_client(settings.config_container)
                await self._config.read()
        except AzureError as exc:
            await self.close()
            raise BackendUnavailableError(f"Could not open Cosmos containers: {type(exc).__name__}") from exc
        logger.info("Connected to Cosmos database %s (containers %s, %s)", settings.cosmos_database,
                    settings.rows_container, settings.config_container)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
        if self._credential is not None:
            await self._credential.close()
            self._credential = None

    async def list_tables(self) -> list[TableRecord]:
        query = "SELECT * FROM c WHERE c.pk = @pk"
        docs = await self._query(self._config_container, query, [{"name": "@pk", "value": CONFIG_TABLE_PK}],
                                 CONFIG_TABLE_PK)
        return sorted((_record_from_doc(doc) for doc in docs), key=lambda record: record.definition.name)

    async def get_table(self, table: str) -> TableRecord | None:
        try:
            doc = await self._config_container.read_item(item=_config_id(table), partition_key=CONFIG_TABLE_PK)
        except CosmosResourceNotFoundError:
            return None
        except AzureError as exc:
            raise _unavailable(exc, table) from exc
        return _record_from_doc(doc)

    async def get_row(self, table: str, key: tuple[str, ...]) -> Row | None:
        try:
            doc = await self._rows_container.read_item(item=encode_row_id(key), partition_key=table)
        except CosmosResourceNotFoundError:
            return None
        except AzureError as exc:
            raise _unavailable(exc, table) from exc
        return _row_from_doc(doc)

    async def load_rows(self, table: str) -> list[Row]:
        docs = await self._query(self._rows_container, 'SELECT c.key, c["values"] FROM c', [], table)
        return [_row_from_doc(doc) for doc in docs]

    async def query_rows(self, table: str, search: str | None, offset: int, limit: int) -> tuple[list[Row], int]:
        # Fixed query texts; every caller-supplied value is a bound parameter.
        parameters: list[dict[str, Any]] = []
        if search:
            count_query, page_query = _COUNT_ROWS_MATCHING, _PAGE_ROWS_MATCHING
            parameters.append({"name": "@search", "value": search})
        else:
            count_query, page_query = _COUNT_ROWS, _PAGE_ROWS
        total_docs = await self._query(self._rows_container, count_query, parameters, table)
        page_parameters = [*parameters, {"name": "@offset", "value": offset}, {"name": "@limit", "value": limit}]
        docs = await self._query(self._rows_container, page_query, page_parameters, table)
        return [_row_from_doc(doc) for doc in docs], int(total_docs[0]) if total_docs else 0

    async def replace_table(
        self, definition: TableDefinition, rows: Sequence[Row], upload: UploadInfo
    ) -> ReplaceResult:
        table = definition.name
        try:
            existing_ids = set(await self._query(self._rows_container, "SELECT VALUE c.id FROM c", [], table))
            docs = [_row_doc(definition, row) for row in rows]
            new_ids = {doc["id"] for doc in docs}

            # Upsert before deleting, so keys present in both the old and new data never disappear mid-replace.
            # All rows share one partition (the table), so they go in transactional batches of up to 100.
            upsert_batches = _batches([("upsert", (doc,)) for doc in docs])
            await _run_bounded(upsert_batches, lambda batch: self._execute_batch(table, batch),
                               self._settings.upload_concurrency)
            stale_ids = existing_ids - new_ids
            delete_batches = _batches([("delete", (row_id,)) for row_id in sorted(stale_ids)])
            await _run_bounded(delete_batches, lambda batch: self._execute_batch(table, batch),
                               self._settings.upload_concurrency)

            stats = TableStats(row_count=len(docs), last_upload_at=datetime.now(UTC),
                               last_upload_file=upload.file_name, last_upload_by=upload.actor)
            await self._config_container.upsert_item(_config_doc(definition, stats))
        except AzureError as exc:
            raise _unavailable(exc, table) from exc
        return ReplaceResult(upserted=len(docs), removed=len(stale_ids))

    async def _execute_batch(self, table: str, operations: list[tuple[str, tuple[Any, ...]]]) -> None:
        await self._rows_container.execute_item_batch(batch_operations=operations, partition_key=table)

    async def _query(self, container: ContainerProxy, query: str, parameters: list[dict[str, Any]],
                     partition_key: str) -> list[Any]:
        try:
            return [item async for item in container.query_items(query=query, parameters=parameters,
                                                                  partition_key=partition_key,
                                                                  max_item_count=QUERY_PAGE_SIZE)]
        except AzureError as exc:
            raise _unavailable(exc, partition_key) from exc

    @property
    def _rows_container(self) -> ContainerProxy:
        if self._rows is None:
            raise BackendUnavailableError("Cosmos store is not open")
        return self._rows

    @property
    def _config_container(self) -> ContainerProxy:
        if self._config is None:
            raise BackendUnavailableError("Cosmos store is not open")
        return self._config


async def _run_bounded(items: Iterable[T], worker: Callable[[T], Awaitable[Any]], concurrency: int) -> None:
    """Run `worker` over `items` with at most `concurrency` calls in flight; the first failure cancels the rest."""
    iterator = iter(items)

    async def drain() -> None:
        for item in iterator:
            await worker(item)

    async with asyncio.TaskGroup() as group:
        for _ in range(concurrency):
            group.create_task(drain())


def _batches(operations: list[tuple[str, tuple[Any, ...]]]) -> list[list[tuple[str, tuple[Any, ...]]]]:
    """Split operations into Cosmos transactional batches (max 100 operations, 2 MB request)."""
    batches: list[list[tuple[str, tuple[Any, ...]]]] = []
    current: list[tuple[str, tuple[Any, ...]]] = []
    current_bytes = 0
    for operation in operations:
        size = len(json.dumps(operation[1], ensure_ascii=False).encode("utf-8"))
        if current and (len(current) >= MAX_BATCH_OPERATIONS or current_bytes + size > MAX_BATCH_BYTES):
            batches.append(current)
            current, current_bytes = [], 0
        current.append(operation)
        current_bytes += size
    if current:
        batches.append(current)
    return batches


def _unavailable(exc: Exception, table: str | None) -> BackendUnavailableError:
    # Type name only: SDK messages can include request details we don't want to surface.
    logger.warning("Cosmos operation failed for table %s: %s", table, type(exc).__name__)
    return BackendUnavailableError(f"Lookup storage is unavailable ({type(exc).__name__})", table)


def _config_id(table: str) -> str:
    return f"{CONFIG_TABLE_PK}::{table}"


def _row_doc(definition: TableDefinition, row: Row) -> dict[str, Any]:
    return {
        "id": encode_row_id(row.key),
        "table_name": definition.name,
        "key": list(row.key),
        "key_text": key_text(row.key),
        "key_parts": dict(zip(definition.key_columns, row.key, strict=True)),
        "values": dict(row.values),
    }


def _row_from_doc(doc: dict[str, Any]) -> Row:
    return Row(key=tuple(doc["key"]), values=MappingProxyType(dict(doc["values"])))


def _config_doc(definition: TableDefinition, stats: TableStats) -> dict[str, Any]:
    return {
        "id": _config_id(definition.name),
        "pk": CONFIG_TABLE_PK,
        "table_name": definition.name,
        "definition": definition.model_dump(mode="json"),
        "stats": stats.model_dump(mode="json"),
    }


def _record_from_doc(doc: dict[str, Any]) -> TableRecord:
    return TableRecord.model_validate({"definition": doc["definition"], "stats": doc.get("stats") or {}})
