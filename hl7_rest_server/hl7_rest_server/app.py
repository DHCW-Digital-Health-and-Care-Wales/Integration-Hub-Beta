from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from hl7_rest_server.api_constant import ApiConstants
from hl7_rest_server.app_config import AppConfig
from hl7_rest_server.routes import health, messages
from hl7_rest_server.runtime import RuntimeContext, build_runtime_context

logger = logging.getLogger(__name__)


def create_app(context: RuntimeContext | None = None) -> FastAPI:
    """Build the FastAPI application.

    Args:
        context: Pre-wired runtime dependencies. When omitted, the context is
            built from environment configuration (which connects to Service Bus).
            Tests inject a context with mocked dependencies.
    """
    if context is None:
        context = build_runtime_context(AppConfig.read_env_config())

    config = context.config
    swagger_enabled = config.swagger_enabled

    app = FastAPI(
        title=ApiConstants.APPLICATION_NAME,
        version=ApiConstants.VERSION,
        docs_url="/docs" if swagger_enabled else None,
        redoc_url="/redoc" if swagger_enabled else None,
        openapi_url="/openapi.json" if swagger_enabled else None,
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
