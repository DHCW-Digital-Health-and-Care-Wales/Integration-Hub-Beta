from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from lookup_service.api.dependencies import get_store
from lookup_service.errors import LookupServiceError
from lookup_service.models import LookupResult
from lookup_service.resolver import named_key_params, resolve_lookup
from lookup_service.store.base import TableStore

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=Path(__file__).resolve().parent / "templates")

SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'; form-action 'self'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}


@router.get("/", response_class=HTMLResponse)
async def overview(
    request: Request,
    store: Annotated[TableStore, Depends(get_store)],
    table: str | None = None,
) -> HTMLResponse:
    """Overview: loaded tables plus a per-table lookup tester (plain GET form, no JavaScript)."""
    submitted: dict[str, str] = {}
    result: LookupResult | None = None
    error: LookupServiceError | None = None
    if table:
        try:
            submitted = named_key_params(table, request.query_params.multi_items())
            result = await resolve_lookup(store, table, named=submitted)
        except LookupServiceError as exc:
            error = exc

    tables = await store.list_tables()
    context = {
        "tables": tables,
        "composite_count": sum(1 for t in tables if len(t.key_columns) > 1),
        "tried_table": table,
        "submitted": submitted,
        "result": result,
        "error": error,
    }
    return templates.TemplateResponse(request, "overview.html", context, headers=SECURITY_HEADERS)
