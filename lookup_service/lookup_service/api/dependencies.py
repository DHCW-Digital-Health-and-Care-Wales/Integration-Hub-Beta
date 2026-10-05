from __future__ import annotations

from fastapi import Request

from lookup_service.errors import StoreNotReadyError
from lookup_service.store.base import TableStore


def get_store(request: Request) -> TableStore:
    store: TableStore | None = getattr(request.app.state, "store", None)
    if store is None:
        raise StoreNotReadyError("Lookup tables are not loaded yet")
    return store
