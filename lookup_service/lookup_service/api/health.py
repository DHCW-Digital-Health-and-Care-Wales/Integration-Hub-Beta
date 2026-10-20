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
    """Readiness: table definitions are loaded and preloaded tables are in memory."""
    resolver = getattr(request.app.state, "resolver", None)
    if resolver is None:
        return JSONResponse(status_code=503, content={"status": "not_ready"})
    return {"status": "ready", "tables": len(resolver.summaries()), "source": resolver.store.source}
