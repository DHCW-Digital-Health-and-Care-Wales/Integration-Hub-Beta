from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def live() -> dict[str, str]:
    """Liveness: the process is serving HTTP. No dependency checks."""
    return {"status": "ok"}


@router.get("/ready", response_model=None)
async def ready(request: Request) -> dict[str, object] | JSONResponse:
    """Readiness: lookup tables are loaded and can be served."""
    store = getattr(request.app.state, "store", None)
    if store is None:
        return JSONResponse(status_code=503, content={"status": "not_ready"})
    tables = await store.list_tables()
    return {"status": "ready", "tables": len(tables)}
