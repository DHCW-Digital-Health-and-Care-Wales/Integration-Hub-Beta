"""Builds the FastAPI ASGI app: route registration, OpenAPI docs, request-size guarding.

Kept separate from ``rest_server_application.py`` so it can be unit tested with a mocked
``RestMessageProcessor`` and no environment/Service Bus wiring.
"""
from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Callable, Optional

from fastapi import FastAPI, Request, Response

from rest_server.errors import RequestError
from rest_server.message_processor import RestMessageProcessor

LifespanFactory = Callable[[FastAPI], AbstractAsyncContextManager[None]]


def build_fastapi_app(
    processor: RestMessageProcessor,
    endpoint_path: str,
    max_request_size_bytes: int,
    content_adapter_name: str,
    validator_type: str,
    output_format: str,
    lifespan: Optional[LifespanFactory] = None,
) -> FastAPI:
    request_content_type = processor.content_type.split(";", 1)[0].strip()

    app = FastAPI(
        title="REST server",
        description=(
            "Configurable HTTP/REST ingestion endpoint. This running instance is configured "
            f"with content adapter **{content_adapter_name}**, validator **{validator_type}**, "
            f"output format **{output_format}**."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    async def ingest_endpoint(request: Request) -> Response:
        try:
            raw_bytes = await _read_body_within_limit(request, max_request_size_bytes)
        except RequestError as limit_error:
            return _build_error_response(processor, limit_error.http_status, limit_error.message)

        if not raw_bytes:
            return _build_error_response(processor, 400, "Request body is empty.")

        try:
            raw_body = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return _build_error_response(processor, 400, "Request body must be UTF-8 encoded.")

        status_code, response_body = processor.process(raw_body)
        return Response(content=response_body, status_code=status_code, media_type=processor.content_type)

    app.add_api_route(
        endpoint_path,
        ingest_endpoint,
        methods=["POST"],
        summary="Ingest and validate a payload",
        description=(
            f"Accepts a `{request_content_type}` POST body, unwraps it with the "
            f"`{content_adapter_name}` content adapter, validates it with the `{validator_type}` "
            "validator, and forwards the validated payload to the configured Service Bus "
            "queue/topic. The ack/error response is built by the same content adapter."
        ),
        responses={
            200: {"description": "Validated and forwarded.", "content": {request_content_type: {}}},
            400: {
                "description": "Malformed request, or payload failed schema/business validation.",
                "content": {request_content_type: {}},
            },
            403: {
                "description": "Source identifier not in the configured allow-list.",
                "content": {request_content_type: {}},
            },
            413: {
                "description": "Request body exceeds the configured size limit.",
                "content": {request_content_type: {}},
            },
            500: {"description": "Unexpected server error.", "content": {request_content_type: {}}},
        },
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    request_content_type: {
                        "schema": {"type": "string"},
                        "example": "<Document>...</Document>",
                    }
                },
            }
        },
    )

    @app.get("/health", summary="Liveness check", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


async def _read_body_within_limit(request: Request, max_size: int) -> bytes:
    """Read the request body as a stream, rejecting it as soon as it exceeds ``max_size``.

    Reading via ``request.stream()`` (rather than ``request.body()``) means the size limit is
    enforced even when no (or an inaccurate) Content-Length header is supplied, e.g. chunked
    transfer encoding - protecting against unbounded memory use from oversized payloads.
    """
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > max_size:
            raise RequestError(
                "Client",
                f"Request body exceeds configured limit of {max_size} bytes.",
                413,
            )
    return bytes(body)


def _build_error_response(processor: RestMessageProcessor, status_code: int, message: str) -> Response:
    body = processor.content_adapter.build_error_response("Client", message)
    return Response(content=body, status_code=status_code, media_type=processor.content_type)
