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


def _persist(source_id: str, source: dict[str, Any]) -> None:
    """Write a source document, stashing its id under "source_id".

    ``cosmos_store`` treats "id" as Cosmos routing metadata and strips it back out of
    every document it returns (see ``_RESERVED_KEYS``), so relying on "id" surviving
    the round trip silently loses it — ``list_sources()`` would then return sources
    with no usable id, breaking edit/delete. Storing it under "source_id" instead (not
    a reserved key) means it comes back unchanged on read.
    """
    cosmos_store.upsert_document(_PK, source_id, {**source, "source_id": source_id}, doc_type=_DOC_TYPE)


def list_sources() -> list[dict[str, Any]]:
    """Return every configured flow source server, sorted by description."""
    sources = []
    for document in cosmos_store.query_documents(_PK):
        document["id"] = document.pop("source_id", None)
        sources.append(document)
    sources.sort(key=lambda source: str(source.get("description", "")).lower())
    return sources


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
    key = _duplicate_key(source["url"], source["port"])
    if any(_duplicate_key(s["url"], s["port"]) == key for s in list_sources()):
        raise InvalidSourceError(f"A source for {source['url']}:{source['port']} already exists")

    source["id"] = str(uuid.uuid4())
    _persist(source["id"], source)
    return source


def update_source(source_id: str, description: str, url: str, port: Any) -> dict[str, Any]:
    """Validate and overwrite an existing flow source server, returning the stored document.

    Raises InvalidSourceError if the new url:port (case-insensitive) collides with a
    *different* existing source — the source being edited is excluded from that check.
    """
    source = _validate_source(description, url, port)
    key = _duplicate_key(source["url"], source["port"])
    if any(s["id"] != source_id and _duplicate_key(s["url"], s["port"]) == key for s in list_sources()):
        raise InvalidSourceError(f"A source for {source['url']}:{source['port']} already exists")

    source["id"] = source_id
    _persist(source_id, source)
    return source


def delete_source(source_id: str) -> None:
    """Permanently remove a flow source server. A no-op if it's already gone."""
    cosmos_store.delete_document(_PK, source_id)


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
            errors.append(f"Row {row_number}: {exc}")
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

    Returns a summary ``{"imported": <count>, "errors": [...]}`` — rows that fail
    validation, duplicate another row in the same file, or duplicate an already-stored
    source (by url:port, case-insensitive) are reported but don't abort the rest of
    the import.
    """
    valid_rows, errors = parse_csv(file_content)

    existing_keys = {_duplicate_key(s["url"], s["port"]) for s in list_sources()}
    imported = 0
    for row in valid_rows:
        key = _duplicate_key(row["url"], row["port"])
        if key in existing_keys:
            errors.append(f"{row['description']} ({row['url']}:{row['port']}): already exists, skipped")
            continue
        row["id"] = str(uuid.uuid4())
        _persist(row["id"], row)
        imported += 1

    return {"imported": imported, "errors": errors}

