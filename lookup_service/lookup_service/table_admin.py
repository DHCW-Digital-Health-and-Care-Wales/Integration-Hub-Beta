"""Replacing a table's data from an uploaded CSV, shared by the API and the GUI."""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePath
from typing import Any

from pydantic import ValidationError

from lookup_service.config import Settings
from lookup_service.csv_import import build_definition, decode_csv_bytes, import_rows, read_csv
from lookup_service.errors import (
    InvalidUploadError,
    ReadOnlyStoreError,
    UploadTooLargeError,
    WritesDisabledError,
)
from lookup_service.mapping.model import RecordMapping
from lookup_service.models import TABLE_NAME_PATTERN, UploadInfo, UploadResult
from lookup_service.resolver import LookupResolver

logger = logging.getLogger(__name__)

# Replaced by the authenticated principal in Phase 2.
ANONYMOUS_ACTOR = "unauthenticated"
MAX_FILE_NAME_LENGTH = 200
_TABLE_NAME_RE = re.compile(TABLE_NAME_PATTERN)


@dataclass(frozen=True)
class UploadRequest:
    table: str
    data: bytes
    file_name: str | None
    # None means "keep the existing table's definition".
    definition_settings: Mapping[str, Any] | None = None
    mapping: RecordMapping | None = None
    actor: str = ANONYMOUS_ACTOR


def ensure_writes_allowed(settings: Settings, resolver: LookupResolver) -> None:
    if not settings.writes_enabled:
        raise WritesDisabledError("Uploads are disabled in this environment until authentication is in place")
    if not resolver.store.writable:
        raise ReadOnlyStoreError("Tables are served from seed files; configure COSMOS_ENDPOINT to enable uploads")


async def replace_table_from_csv(settings: Settings, resolver: LookupResolver, request: UploadRequest) -> UploadResult:
    """Validate the whole file first, then replace the table. Nothing is written if any row is invalid."""
    ensure_writes_allowed(settings, resolver)
    table = request.table
    if not _TABLE_NAME_RE.fullmatch(table):
        raise InvalidUploadError(f"Invalid table name; must match {TABLE_NAME_PATTERN}")
    if len(request.data) > settings.max_upload_bytes:
        raise UploadTooLargeError(f"File exceeds the {settings.max_upload_mb} MB upload limit", table)

    document, csv_errors = read_csv(decode_csv_bytes(request.data))
    if csv_errors:
        raise InvalidUploadError("The CSV file is invalid; nothing was changed", table, [str(e) for e in csv_errors])

    created = not resolver.has_table(table)
    if request.definition_settings is not None:
        try:
            definition = build_definition(table, document.header, request.definition_settings)
        except ValidationError as exc:
            raise InvalidUploadError("The table definition is invalid; nothing was changed", table,
                                     _validation_messages(exc)) from exc
    elif not created:
        definition = resolver.definition(table)
    else:
        raise InvalidUploadError(f"Table {table!r} does not exist; supply a table definition to create it", table)

    result = import_rows(document, definition, request.mapping)
    if result.errors:
        raise InvalidUploadError(f"{len(result.errors)} problem(s) found; nothing was changed", table,
                                 result.error_messages())
    if not result.rows:
        raise InvalidUploadError("The file has no data rows; nothing was changed", table)

    started = time.perf_counter()
    async with resolver.upload_lock:
        replaced = await resolver.store.replace_table(
            definition, list(result.rows.values()),
            UploadInfo(actor=request.actor, file_name=_safe_file_name(request)),
        )
        await resolver.refresh_table(table)
    duration_ms = round((time.perf_counter() - started) * 1000)
    logger.info("Replaced table %s: %d row(s), %d removed, %d ms", table, len(result.rows), replaced.removed,
                duration_ms)
    return UploadResult(table=table, row_count=len(result.rows), upserted=replaced.upserted, removed=replaced.removed,
                        duration_ms=duration_ms, created=created)


def _safe_file_name(request: UploadRequest) -> str | None:
    if not request.file_name:
        return None
    return PurePath(request.file_name.replace("\\", "/")).name[:MAX_FILE_NAME_LENGTH] or None


def _validation_messages(exc: ValidationError) -> list[str]:
    # pydantic's `msg` doesn't include the rejected input value.
    return [f"{'.'.join(str(part) for part in error['loc']) or 'definition'}: {error['msg']}" for error in exc.errors()]
