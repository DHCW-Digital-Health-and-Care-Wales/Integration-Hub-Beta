from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from lookup_service.api.dependencies import get_store
from lookup_service.models import ErrorResponse, LookupResult
from lookup_service.resolver import named_key_params, resolve_lookup
from lookup_service.store.base import TableStore

router = APIRouter(prefix="/api/v1", tags=["lookup"])

_ERRORS: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse, "description": "table_not_found or key_not_found"},
    422: {"model": ErrorResponse, "description": "invalid_key (missing, mixed, wrong arity or empty parts)"},
}


@router.get("/lookup/{table}", response_model=LookupResult, responses=_ERRORS)
async def lookup(
    table: str,
    request: Request,
    store: Annotated[TableStore, Depends(get_store)],
    k: Annotated[
        list[str] | None,
        Query(description="Positional key part; repeat for composite keys. Alternatively use key.<part>=value."),
    ] = None,
) -> LookupResult:
    named = named_key_params(table, request.query_params.multi_items())
    return await resolve_lookup(store, table, k or [], named)
