from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import ValidationError
from starlette.datastructures import UploadFile as StarletteUploadFile

from lookup_service.api.dependencies import get_resolver, get_settings
from lookup_service.config import Settings
from lookup_service.errors import InvalidUploadError, UploadTooLargeError
from lookup_service.mapping.model import RecordMapping
from lookup_service.models import ErrorResponse, RowOut, RowsPage, TableDetail, TableSummary, UploadResult
from lookup_service.resolver import LookupResolver
from lookup_service.table_admin import UploadRequest, ensure_writes_allowed, replace_table_from_csv

router = APIRouter(prefix="/api/v1", tags=["tables"])

MAX_PAGE_SIZE = 200
_UPLOAD_ERRORS: dict[int | str, dict[str, Any]] = {
    403: {"model": ErrorResponse, "description": "writes_disabled"},
    409: {"model": ErrorResponse, "description": "read_only (file-backed store)"},
    413: {"model": ErrorResponse, "description": "upload_too_large"},
    422: {"model": ErrorResponse, "description": "invalid_upload, with per-line `errors`"},
    503: {"model": ErrorResponse, "description": "backend_unavailable"},
}


@router.get("/tables", response_model=list[TableSummary])
async def list_tables(resolver: Annotated[LookupResolver, Depends(get_resolver)]) -> list[TableSummary]:
    return resolver.summaries()


@router.get("/tables/{table}", response_model=TableDetail, responses={404: {"model": ErrorResponse}})
async def get_table(table: str, resolver: Annotated[LookupResolver, Depends(get_resolver)]) -> TableDetail:
    return resolver.detail(table)


@router.get("/tables/{table}/rows", response_model=RowsPage, responses={404: {"model": ErrorResponse}})
async def list_rows(
    table: str,
    resolver: Annotated[LookupResolver, Depends(get_resolver)],
    search: Annotated[str | None, Query(max_length=200, description="Case-insensitive key substring")] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 50,
) -> RowsPage:
    resolver.definition(table)
    rows, total = await resolver.store.query_rows(table, search or None, offset, limit)
    return RowsPage(table=table, total=total, offset=offset, limit=limit, search=search or None,
                    rows=[RowOut(key=list(row.key), values=dict(row.values)) for row in rows])


@router.post("/tables/{table}/uploads", response_model=UploadResult, status_code=201, responses=_UPLOAD_ERRORS)
async def upload_table(
    table: str,
    resolver: Annotated[LookupResolver, Depends(get_resolver)],
    settings: Annotated[Settings, Depends(get_settings)],
    file: Annotated[UploadFile, File(description="CSV file with a header row (UTF-8)")],
    definition: Annotated[
        str | None,
        Form(description="JSON table definition (key_columns, value_columns, ...). Required for a new table; "
                         "replaces the existing definition when given."),
    ] = None,
    mapping: Annotated[
        str | None,
        Form(description='JSON column mapping {"key": {...}, "values": {...}}; defaults to matching column names'),
    ] = None,
) -> UploadResult:
    """Replace a table's rows (and optionally its definition) from a CSV file. Replace mode only."""
    ensure_writes_allowed(settings, resolver)
    data = await read_upload(file, settings)
    request = UploadRequest(
        table=table,
        data=data,
        file_name=file.filename,
        definition_settings=_parse_json_object(definition, "definition", table),
        mapping=_parse_mapping(mapping, table),
    )
    return await replace_table_from_csv(settings, resolver, request)


async def read_upload(file: StarletteUploadFile, settings: Settings) -> bytes:
    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise UploadTooLargeError(f"File exceeds the {settings.max_upload_mb} MB upload limit")
    return data


def _parse_json_object(raw: str | None, field: str, table: str) -> dict[str, Any] | None:
    if raw is None or not raw.strip():
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InvalidUploadError(f"{field} is not valid JSON", table) from exc
    if not isinstance(parsed, dict):
        raise InvalidUploadError(f"{field} must be a JSON object", table)
    return parsed


def _parse_mapping(raw: str | None, table: str) -> RecordMapping | None:
    parsed = _parse_json_object(raw, "mapping", table)
    if parsed is None:
        return None
    try:
        return RecordMapping.model_validate(parsed)
    except ValidationError as exc:
        raise InvalidUploadError("mapping is invalid", table,
                                 [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()]) from exc
