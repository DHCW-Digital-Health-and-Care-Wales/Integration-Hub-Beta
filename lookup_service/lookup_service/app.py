from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from lookup_service.api import health, lookup, tables
from lookup_service.config import Settings
from lookup_service.errors import LookupServiceError
from lookup_service.gui import pages
from lookup_service.models import ErrorResponse
from lookup_service.store.base import TableStore
from lookup_service.store.file_store import FileTableStore

logger = logging.getLogger(__name__)

APPLICATION_NAME = "Integration Hub Lookup Service"
VERSION = "0.1.0"
STATIC_DIR = Path(__file__).resolve().parent / "gui" / "static"


def create_app(settings: Settings | None = None, store: TableStore | None = None) -> FastAPI:
    """Build the FastAPI application.

    Args:
        settings: Configuration; read from the environment when omitted.
        store: Pre-built table store (tests). When omitted, seed files are loaded during startup and
            the app reports not-ready until loading completes.
    """
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if app.state.store is None:
            app.state.store = FileTableStore.load(settings.seed_dir)
        yield

    app = FastAPI(
        title=APPLICATION_NAME,
        version=VERSION,
        lifespan=lifespan,
        docs_url="/docs" if settings.swagger_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.swagger_enabled else None,
    )
    app.state.settings = settings
    app.state.store = store

    @app.exception_handler(LookupServiceError)
    async def handle_lookup_error(request: Request, exc: LookupServiceError) -> JSONResponse:
        body = ErrorResponse(error=exc.error_code, detail=exc.detail, table=exc.table)
        return JSONResponse(status_code=exc.status_code, content=body.model_dump())

    app.include_router(health.router)
    app.include_router(lookup.router)
    app.include_router(tables.router)
    app.include_router(pages.router)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app
