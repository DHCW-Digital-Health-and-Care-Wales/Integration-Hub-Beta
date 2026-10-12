from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from lookup_service import __version__
from lookup_service.api import health, lookup, tables
from lookup_service.config import Settings
from lookup_service.errors import LookupServiceError
from lookup_service.gui import pages
from lookup_service.models import ErrorResponse
from lookup_service.resolver import LookupResolver
from lookup_service.seed import import_missing_seed_tables
from lookup_service.store.base import TableStore
from lookup_service.store.cosmos_store import CosmosTableStore
from lookup_service.store.file_store import FileTableStore

logger = logging.getLogger(__name__)

APPLICATION_NAME = "Integration Hub Lookup Service"
VERSION = __version__
STATIC_DIR = Path(__file__).resolve().parent / "gui" / "static"


def build_store(settings: Settings) -> TableStore:
    """Cosmos when COSMOS_ENDPOINT is set; otherwise read-only tables from the seed files."""
    if settings.cosmos_endpoint:
        return CosmosTableStore(settings)
    logger.info("COSMOS_ENDPOINT not set; serving read-only tables from %s", settings.seed_dir)
    return FileTableStore.load(settings.seed_dir)


def create_app(settings: Settings | None = None, store: TableStore | None = None) -> FastAPI:
    """Build the FastAPI application.

    Args:
        settings: Configuration; read from the environment when omitted.
        store: Pre-built table store (tests). When omitted, one is built from settings during startup.
            Either way, startup seeds a writable store and loads tables; the app reports not-ready
            until that completes.
    """
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        owns_store = store is None
        active_store = store or build_store(settings)
        await active_store.open()
        try:
            await import_missing_seed_tables(active_store, settings.seed_dir)
            resolver = LookupResolver(active_store, settings.default_ttl_seconds, settings.cache_max_entries)
            await resolver.start()
            app.state.resolver = resolver
            yield
        finally:
            app.state.resolver = None
            if owns_store:
                await active_store.close()

    app = FastAPI(
        title=APPLICATION_NAME,
        version=VERSION,
        lifespan=lifespan,
        docs_url="/docs" if settings.swagger_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.swagger_enabled else None,
    )
    app.state.settings = settings
    app.state.resolver = None

    @app.exception_handler(LookupServiceError)
    async def handle_lookup_error(request: Request, exc: LookupServiceError) -> JSONResponse:
        body = ErrorResponse(error=exc.error_code, detail=exc.detail, table=exc.table, errors=exc.errors)
        content = body.model_dump()
        if body.errors is None:
            content.pop("errors")
        return JSONResponse(status_code=exc.status_code, content=content)

    app.include_router(health.router)
    app.include_router(lookup.router)
    app.include_router(tables.router)
    app.include_router(pages.router)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app
