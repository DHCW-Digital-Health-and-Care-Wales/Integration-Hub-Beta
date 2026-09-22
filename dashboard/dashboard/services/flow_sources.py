"""Persistence and validation for user-managed "Flow Source Server" entries.

Powers the Network Test page's configuration screen (gear icon), where support staff
maintain a list of flow source servers (description/url/port) either by adding them
one at a time or bulk-importing a CSV. Each entry is stored as its own Cosmos document
(see ``cosmos_store``) partitioned on a fixed key, mirroring the pattern already used
for tested-endpoint history in ``network_test.py``.
"""

from __future__ import annotations

import csv
import io
import uuid
from typing import Any

from azure.cosmos.exceptions import CosmosResourceExistsError

from dashboard.services import cosmos_store
from dashboard.services.network_test import InvalidTargetError, validate_host, validate_port

# Fixed partition key — this is a small, low-cardinality set of documents (a handful
# of flow source servers), so a single partition keeps every list read a
# single-partition query.
_PK = "flow-source-server"
_DOC_TYPE = "flow_source_server"

_MAX_DESCRIPTION_LENGTH = 200
_CSV_REQUIRED_FIELDS = ("description", "url", "port")


class InvalidSourceError(ValueError):
    """Raised when a supplied source's description/url/port fails validation."""

    def __init__(self, message: str):
        super().__init__(message)
        self.safe_message = message


class SourcePersistenceError(RuntimeError):
    """Raised when a source change could not be saved durably."""

    def __init__(self, message: str):
        super().__init__(message)
        self.safe_message = message


_PERSISTENCE_DISABLED_MESSAGE = "Source persistence is not configured."
_PERSISTENCE_UNAVAILABLE_MESSAGE = "Source persistence is currently unavailable."


def _validate_description(description: str) -> str:
    if not isinstance(description, str):
        raise InvalidSourceError("Description must be a string")
    description = description.strip()
    if not description:
        raise InvalidSourceError("Description must not be empty")
    if len(description) > _MAX_DESCRIPTION_LENGTH:
        raise InvalidSourceError(f"Description is too long (max {_MAX_DESCRIPTION_LENGTH} characters)")
    return description


def _validate_source(description: str, url: str, port: Any) -> dict[str, Any]:
    """Validate a source's fields, raising InvalidSourceError on the first problem.

    ``url`` is validated as a hostname or IP address (the same rule used to validate
    Network Test targets) — this is the boundary check that keeps free-text input from
    ever reaching a socket call unvalidated.
    """
    try:
        validated_url = validate_host(url)
        validated_port = validate_port(port)
    except InvalidTargetError as exc:
        raise InvalidSourceError(str(exc)) from exc

    return {
        "description": _validate_description(description),
        "url": validated_url,
        "port": validated_port,
    }


def _duplicate_key(url: str, port: int) -> tuple[str, int]:
    """Identify a source by url:port, case-insensitively — the target it tests."""
    return (url.lower(), port)


def _storage_id(key: tuple[str, int]) -> str:
    """Return the deterministic Cosmos id for a source endpoint."""
    return f"flow-source:{key[0]}:{key[1]}"


def _with_internal_ids(document: dict[str, Any]) -> dict[str, Any]:
    """Map persisted IDs into the public id plus an internal storage id."""
    source_id = document.get("source_id")
    source = {k: v for k, v in document.items() if k not in {"source_id", "storage_id"}}
    source["id"] = source_id
    source["_storage_id"] = str(document.get("storage_id") or source_id)
    return source


def _public_source(source: dict[str, Any]) -> dict[str, Any]:
    """Strip internal persistence metadata from a source record."""
    return {k: v for k, v in source.items() if k != "_storage_id"}


def _list_source_documents() -> list[dict[str, Any]]:
    """Return every configured source including internal persistence metadata."""
    sources = [_with_internal_ids(document) for document in cosmos_store.query_documents(_PK)]
    sources.sort(key=lambda source: str(source.get("description", "")).lower())
    return sources


def _find_source_document(source_id: str) -> dict[str, Any] | None:
    """Return one configured source by its public id."""
    for source in _list_source_documents():
        if source["id"] == source_id:
            return source
    return None


def _ensure_persistence_configured() -> None:
    """Reject writes when this dashboard instance has no durable source storage."""
    if not cosmos_store.is_configured():
        raise SourcePersistenceError(_PERSISTENCE_DISABLED_MESSAGE)


def _persist(source_id: str, source: dict[str, Any], storage_id: str | None = None) -> None:
    """Write a source document, stashing its id under "source_id".

    ``cosmos_store`` treats "id" as Cosmos routing metadata and strips it back out of
    every document it returns (see ``_RESERVED_KEYS``), so relying on "id" surviving
    the round trip silently loses it — ``list_sources()`` would then return sources
    with no usable id, breaking edit/delete. Storing it under "source_id" instead (not
    a reserved key) means it comes back unchanged on read.
    """
    resolved_storage_id = storage_id or str(source.get("_storage_id") or source_id)
    persisted_source = {k: v for k, v in source.items() if not k.startswith("_")}
    if not cosmos_store.upsert_document(
        _PK,
        resolved_storage_id,
        {**persisted_source, "source_id": source_id, "storage_id": resolved_storage_id},
        doc_type=_DOC_TYPE,
    ):
        raise SourcePersistenceError(_PERSISTENCE_UNAVAILABLE_MESSAGE)


def _create(source_id: str, source: dict[str, Any], key: tuple[str, int]) -> str:
    """Create a source document atomically, failing if another source already owns the key."""
    storage_id = _storage_id(key)
    persisted_source = {k: v for k, v in source.items() if not k.startswith("_")}
    try:
        created = cosmos_store.create_document(
            _PK,
            storage_id,
            {**persisted_source, "source_id": source_id, "storage_id": storage_id},
            doc_type=_DOC_TYPE,
        )
    except CosmosResourceExistsError as exc:
        raise InvalidSourceError(f"A source for {source['url']}:{source['port']} already exists") from exc

    if not created:
        raise SourcePersistenceError(_PERSISTENCE_UNAVAILABLE_MESSAGE)

    return storage_id


def list_sources() -> list[dict[str, Any]]:
    """Return every configured flow source server, sorted by description."""
    return [_public_source(source) for source in _list_source_documents()]


def list_sources_as_endpoint_options() -> list[dict[str, Any]]:
    """Return configured flow source servers as (label, host, port) dropdown options.

    Same shape as ``network_test.build_endpoint_options()``'s output, for the Network
    Test page's "Flow Source Server" picker — this is the only source of that dropdown's
    data (it is not merged with ARM-discovered flow definitions).
    """
    return [
        {
            "label": f"{source['description']} ({source['url']}:{source['port']})",
            "host": source["url"],
            "port": source["port"],
        }
        for source in list_sources()
    ]


def add_source(description: str, url: str, port: Any) -> dict[str, Any]:
    """Validate and persist a new flow source server, returning the stored document.

    Raises InvalidSourceError if any field fails validation, or if a source for the
    same url:port (case-insensitive) already exists.
    """
    source = _validate_source(description, url, port)
    _ensure_persistence_configured()
    key = _duplicate_key(source["url"], source["port"])

    source["id"] = str(uuid.uuid4())
    source["_storage_id"] = _create(source["id"], source, key)
    return _public_source(source)


def update_source(source_id: str, description: str, url: str, port: Any) -> dict[str, Any]:
    """Validate and overwrite an existing flow source server, returning the stored document.

    Raises InvalidSourceError if the new url:port (case-insensitive) collides with a
    *different* existing source — the source being edited is excluded from that check.
    """
    source = _validate_source(description, url, port)
    _ensure_persistence_configured()
    existing = _find_source_document(source_id)
    if existing is None:
        raise InvalidSourceError("Source not found.")
    existing_key = _duplicate_key(existing["url"], existing["port"]) if existing else None
    new_key = _duplicate_key(source["url"], source["port"])
    source["id"] = source_id
    source["_storage_id"] = existing["_storage_id"]

    if existing_key is None or existing_key == new_key:
        _persist(source_id, source)
        return _public_source(source)

    if existing is None:
        raise SourcePersistenceError(_PERSISTENCE_UNAVAILABLE_MESSAGE)
    old_storage_id = str(existing["_storage_id"])
    new_storage_id = _create(source_id, source, new_key)
    if not cosmos_store.delete_document(_PK, old_storage_id):
        cosmos_store.delete_document(_PK, new_storage_id)
        raise SourcePersistenceError(_PERSISTENCE_UNAVAILABLE_MESSAGE)
    source["_storage_id"] = new_storage_id
    return _public_source(source)


def delete_source(source_id: str) -> None:
    """Permanently remove a flow source server. A no-op if it's already gone."""
    source = _find_source_document(source_id)
    storage_id = str(source["_storage_id"]) if source is not None else source_id
    if not cosmos_store.delete_document(_PK, storage_id):
        raise SourcePersistenceError(_PERSISTENCE_UNAVAILABLE_MESSAGE)


def parse_csv(file_content: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Parse CSV text into validated source rows.

    Expects a header row containing "description", "url" and "port" (matched
    case-insensitively, in any column order). Returns ``(valid_rows, errors)`` where
    ``valid_rows`` are dicts with the same shape as :func:`add_source`'s validated
    fields (without an ``id``), and ``errors`` is a list of human-readable messages for
    rows that failed validation — invalid rows are skipped rather than aborting the
    whole import, so a single typo doesn't block every other row.
    """
    reader = csv.DictReader(io.StringIO(file_content))
    if reader.fieldnames is None:
        return [], ["CSV file is empty."]

    normalized_fields = {name.strip().lower(): name for name in reader.fieldnames if name}
    missing = [field for field in _CSV_REQUIRED_FIELDS if field not in normalized_fields]
    if missing:
        return [], [f"CSV header is missing required column(s): {', '.join(missing)}"]

    valid_rows: list[dict[str, Any]] = []
    errors: list[str] = []
    seen_at_row: dict[tuple[str, int], int] = {}  # duplicate key -> first row number seen
    for row_number, row in enumerate(reader, start=2):  # row 1 is the header
        try:
            source = _validate_source(
                row.get(normalized_fields["description"], ""),
                row.get(normalized_fields["url"], ""),
                row.get(normalized_fields["port"], ""),
            )
        except InvalidSourceError as exc:
            errors.append(f"Row {row_number}: {exc.safe_message}")
            continue

        key = _duplicate_key(source["url"], source["port"])
        if key in seen_at_row:
            errors.append(f"Row {row_number}: duplicate of row {seen_at_row[key]} ({source['url']}:{source['port']})")
            continue
        seen_at_row[key] = row_number
        valid_rows.append(source)

    return valid_rows, errors


def import_sources(file_content: str) -> dict[str, Any]:
    """Parse and persist every valid row from an uploaded CSV file.

    Returns a summary ``{"imported": <count>, "errors": [...], "persistence_failed":
    <bool>}`` — rows that fail validation, duplicate another row in the same file, or
    duplicate an already-stored source (by url:port, case-insensitive) are reported but
    don't abort the rest of the import.
    """
    valid_rows, errors = parse_csv(file_content)
    persistence_failed = False
    try:
        _ensure_persistence_configured()
    except SourcePersistenceError as exc:
        errors.append(exc.safe_message)
        return {"imported": 0, "errors": errors, "persistence_failed": True}

    imported = 0
    for row in valid_rows:
        label = f"{row['description']} ({row['url']}:{row['port']})"
        try:
            add_source(row["description"], row["url"], row["port"])
        except InvalidSourceError as exc:
            errors.append(f"{label}: {exc.safe_message}")
        except SourcePersistenceError as exc:
            errors.append(f"{label}: {exc.safe_message}")
            persistence_failed = True
            break
        else:
            imported += 1

    return {"imported": imported, "errors": errors, "persistence_failed": persistence_failed}
