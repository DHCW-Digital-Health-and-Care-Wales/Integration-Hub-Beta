from __future__ import annotations

import math
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.datastructures import FormData, UploadFile

from lookup_service import __version__
from lookup_service.api.dependencies import get_resolver, get_settings
from lookup_service.api.tables import read_upload
from lookup_service.config import Settings
from lookup_service.errors import InvalidUploadError, LookupServiceError
from lookup_service.models import LookupResult
from lookup_service.resolver import NAMED_KEY_PREFIX, LookupResolver, named_key_params
from lookup_service.table_admin import UploadRequest, ensure_writes_allowed, replace_table_from_csv

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=Path(__file__).resolve().parent / "templates")
templates.env.globals["asset_version"] = __version__

PAGE_SIZE = 50
KEY_CASES = ("preserve", "upper", "lower")
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'; form-action 'self'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}


def _render(request: Request, template: str, context: dict[str, Any], status_code: int = 200) -> HTMLResponse:
    return templates.TemplateResponse(request, template, context, status_code=status_code, headers=SECURITY_HEADERS)


def _uploads_blocked_reason(settings: Settings, resolver: LookupResolver) -> str | None:
    try:
        ensure_writes_allowed(settings, resolver)
    except LookupServiceError as exc:
        return exc.detail
    return None


@router.get("/", response_class=HTMLResponse, name="overview")
async def overview(
    request: Request,
    resolver: Annotated[LookupResolver, Depends(get_resolver)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> HTMLResponse:
    tables = resolver.summaries()
    return _render(request, "overview.html", {
        "tables": tables,
        "total_rows": sum(t.row_count for t in tables),
        "composite_count": sum(1 for t in tables if len(t.key_columns) > 1),
        "cached_entries": sum(t.cache.entries for t in tables if t.cache.mode == "ttl"),
        "source": resolver.store.source,
        "uploads_blocked": _uploads_blocked_reason(settings, resolver),
    })


@router.get("/tables/{table}", response_class=HTMLResponse, name="table_page")
async def table_page(
    request: Request,
    table: str,
    resolver: Annotated[LookupResolver, Depends(get_resolver)],
    settings: Annotated[Settings, Depends(get_settings)],
    search: Annotated[str | None, Query(max_length=200)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    uploaded: int | None = None,
) -> HTMLResponse:
    """Table detail: definition, stats, a lookup tester (plain GET form) and paged, searchable rows."""
    if not resolver.has_table(table):
        return _render(request, "not_found.html", {"table": table}, status_code=404)

    result: LookupResult | None = None
    error: LookupServiceError | None = None
    submitted: dict[str, str] = {}
    if any(name.startswith(NAMED_KEY_PREFIX) for name in request.query_params):
        try:
            submitted = named_key_params(table, request.query_params.multi_items())
            result = await resolver.lookup(table, named=submitted)
        except LookupServiceError as exc:
            error = exc

    rows, total = await resolver.store.query_rows(table, search or None, (page - 1) * PAGE_SIZE, PAGE_SIZE)
    return _render(request, "table.html", {
        "table": resolver.detail(table),
        "rows": rows,
        "total": total,
        "page": page,
        "pages": max(1, math.ceil(total / PAGE_SIZE)),
        "search": search or "",
        "result": result,
        "error": error,
        "submitted": submitted,
        "uploaded": uploaded,
        "uploads_blocked": _uploads_blocked_reason(settings, resolver),
    })


@router.get("/upload", response_class=HTMLResponse, name="upload_page")
async def upload_page(
    request: Request,
    resolver: Annotated[LookupResolver, Depends(get_resolver)],
    settings: Annotated[Settings, Depends(get_settings)],
    table: str | None = None,
) -> HTMLResponse:
    return _render(request, "upload.html", _upload_context(resolver, settings, {"table": table or ""}))


@router.post("/upload", response_class=HTMLResponse, name="upload_submit")
async def upload_submit(
    request: Request,
    resolver: Annotated[LookupResolver, Depends(get_resolver)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    # No CSRF token yet: writes are only enabled for ENVIRONMENT=LOCAL until Phase 2 adds auth + CSRF.
    form = await request.form(max_files=1, max_fields=20)
    fields = {name: value for name, value in form.items() if isinstance(value, str)}
    table = fields.get("table", "").strip()
    try:
        ensure_writes_allowed(settings, resolver)
        upload = form.get("file")
        if not isinstance(upload, UploadFile) or not upload.filename:
            raise _form_error("Choose a CSV file to upload", table)
        definition_settings = _definition_from_form(fields) if _wants_definition(fields, resolver, table) else None
        result = await replace_table_from_csv(settings, resolver, UploadRequest(
            table=table,
            data=await read_upload(upload, settings),
            file_name=upload.filename,
            definition_settings=definition_settings,
        ))
    except LookupServiceError as exc:
        context = _upload_context(resolver, settings, fields)
        context["error"] = exc
        return _render(request, "upload.html", context, status_code=exc.status_code)
    finally:
        await _close_files(form)

    target = request.url_for("table_page", table=result.table).include_query_params(uploaded=result.row_count)
    return RedirectResponse(str(target), status_code=303)


def _upload_context(resolver: LookupResolver, settings: Settings, fields: dict[str, Any]) -> dict[str, Any]:
    return {
        "tables": resolver.summaries(),
        "fields": fields,
        "key_cases": KEY_CASES,
        "max_upload_mb": settings.max_upload_mb,
        "default_ttl_seconds": settings.default_ttl_seconds,
        "uploads_blocked": _uploads_blocked_reason(settings, resolver),
        "error": None,
    }


def _wants_definition(fields: dict[str, str], resolver: LookupResolver, table: str) -> bool:
    return not resolver.has_table(table) or fields.get("redefine") == "on"


def _definition_from_form(fields: dict[str, str]) -> dict[str, Any]:
    key_columns = _split_columns(fields.get("key_columns", ""))
    case = fields.get("key_case", "preserve")
    if case not in KEY_CASES:
        raise _form_error("Key case must be one of " + ", ".join(KEY_CASES), fields.get("table"))
    ttl_raw = fields.get("ttl_seconds", "").strip()
    try:
        ttl_seconds = int(ttl_raw) if ttl_raw else None
    except ValueError as exc:
        raise _form_error("TTL must be a whole number of seconds", fields.get("table")) from exc
    return {
        "description": fields.get("description", "").strip(),
        "key_columns": key_columns,
        "value_columns": _split_columns(fields.get("value_columns", "")),
        "default_value_column": fields.get("default_value_column", "").strip() or None,
        "key_normalisation": {column: {"case": case} for column in key_columns} if case != "preserve" else {},
        "ttl_seconds": ttl_seconds,
        "preload": fields.get("preload") == "on",
    }


def _split_columns(raw: str) -> list[str]:
    return [column.strip() for column in raw.split(",") if column.strip()]


def _form_error(message: str, table: str | None) -> LookupServiceError:
    return InvalidUploadError(message, table or None)


async def _close_files(form: FormData) -> None:
    for value in form.values():
        if isinstance(value, UploadFile):
            await value.close()
