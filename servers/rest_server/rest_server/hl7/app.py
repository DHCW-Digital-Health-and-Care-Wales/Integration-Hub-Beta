"""Builds the ``hl7`` pipeline's FastAPI application from a pre-wired runtime context."""
from __future__ import annotations

import logging
from contextlib import AbstractAsyncContextManager
from typing import Callable, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from rest_server.hl7.api_constant import ApiConstants
from rest_server.hl7.routes import health, messages
from rest_server.hl7.runtime import Hl7RuntimeContext

logger = logging.getLogger(__name__)

LifespanFactory = Callable[[FastAPI], AbstractAsyncContextManager[None]]


def create_hl7_app(context: Hl7RuntimeContext, lifespan: Optional[LifespanFactory] = None) -> FastAPI:
    swagger_enabled = context.config.swagger_enabled

    app = FastAPI(
        title=ApiConstants.APPLICATION_NAME,
        version=ApiConstants.VERSION,
        docs_url="/docs" if swagger_enabled else None,
        redoc_url="/redoc" if swagger_enabled else None,
        openapi_url="/openapi.json" if swagger_enabled else None,
        lifespan=lifespan,
    )
    app.state.context = context

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Malformed / missing request body → 400 (not FastAPI's default 422).
        return JSONResponse(
            status_code=400,
            content={"StatusCode": 400, "ErrorMessage": "Invalid or missing request body."},
        )

    app.include_router(health.router)
    app.include_router(messages.router)

    return app
