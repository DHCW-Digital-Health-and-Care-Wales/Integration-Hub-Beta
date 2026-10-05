from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from lookup_service.api.dependencies import get_store
from lookup_service.models import TableSummary
from lookup_service.store.base import TableStore

router = APIRouter(prefix="/api/v1", tags=["tables"])


@router.get("/tables", response_model=list[TableSummary])
async def list_tables(store: Annotated[TableStore, Depends(get_store)]) -> list[TableSummary]:
    return await store.list_tables()
