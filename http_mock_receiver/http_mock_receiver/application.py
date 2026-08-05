"""HTTP Mock Receiver — FastAPI application.

Provides a SOAP endpoint for testing the soap_sender and soap_subscription_sender
services locally without requiring a real downstream SOAP system.

Endpoints:
  POST /soap    — Accept a SOAP envelope, return ACK or fault
  GET  /health  — Simple liveness check

Service Bus forwarding is optional.  When EGRESS_QUEUE_NAME and the relevant
connection config are not set, the service operates in log-only mode — it still
returns valid SOAP responses.
"""
from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from http_mock_receiver.app_config import AppConfig
from http_mock_receiver.soap_handler import parse_soap_request
from http_mock_receiver.soap_response_builder import build_ack_response, build_fault_response

# ── Logging setup ──────────────────────────────────────────────────────────
log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level_str, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
azure_log_level = getattr(logging, os.getenv("AZURE_LOG_LEVEL", "WARN").upper(), logging.WARN)
logging.getLogger("azure").setLevel(azure_log_level)
logger = logging.getLogger(__name__)

# ── Config & optional Service Bus sender ──────────────────────────────────
app_config = AppConfig.read_env_config()

# Initialise Service Bus sender lazily — only when config is present.
_sb_sender = None

if app_config.service_bus_enabled:
    try:
        from message_bus_lib.connection_config import ConnectionConfig
        from message_bus_lib.servicebus_client_factory import ServiceBusClientFactory

        _client_config = ConnectionConfig(
            app_config.service_bus_connection_string,
            app_config.service_bus_namespace,
        )
        _factory = ServiceBusClientFactory(_client_config)
        _sb_sender = _factory.create_queue_sender_client(
            app_config.egress_queue_name,
            app_config.egress_session_id,
        )
        logger.info("Service Bus sender initialised — queue: %s", app_config.egress_queue_name)
    except Exception as exc:
        logger.warning("Service Bus sender could not be initialised: %s — running in log-only mode.", exc)
else:
    logger.info("Service Bus config not provided — running in log-only mode.")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:  # noqa: ARG001
    logger.info("HTTP Mock Receiver starting on %s:%s", app_config.host, app_config.port)
    yield
    if _sb_sender:
        try:
            _sb_sender.close()
            logger.info("Service Bus sender closed.")
        except Exception as exc:
            logger.warning("Error closing Service Bus sender: %s", exc)
    logger.info("HTTP Mock Receiver stopped.")


app = FastAPI(
    title="HTTP Mock Receiver",
    version="0.1.0",
    description="Mock HTTP/SOAP receiver for Integration Hub local testing",
    lifespan=lifespan,
)


# ── Health endpoint ────────────────────────────────────────────────────────

@app.get("/health", response_class=PlainTextResponse)
def health() -> str:
    """Liveness check — always returns 200 OK when the process is running."""
    return "OK"


# ── SOAP endpoint ─────────────────────────────────────────────────────────

@app.post("/soap")
async def soap_endpoint(request: Request) -> Response:
    """Accept an inbound SOAP envelope, log it, and return a SOAP ACK or fault.

    Fault behaviour (mirrors the MLLP mock receiver convention):
    - If the body contains the word "fail" → SOAP fault response
    - Otherwise → SOAP ACK with AA status

    Service Bus forwarding is attempted when configured; failures are logged
    but do not change the SOAP response returned to the caller.
    """
    raw_body = (await request.body()).decode("utf-8", errors="replace")

    logger.info(
        "SOAP request received — %d bytes, Content-Type: %s",
        len(raw_body),
        request.headers.get("content-type", "not set"),
    )
    logger.debug("SOAP body:\n%s", raw_body)

    result = parse_soap_request(raw_body)

    # Log a structured summary of the parsed message.
    logger.info(
        "SOAP parsed — version=%s, control_id=%s, hl7_extracted=%s, fault_requested=%s",
        result.soap_version,
        result.message_control_id,
        result.hl7_payload is not None,
        result.is_fault_requested,
    )

    if result.hl7_payload:
        logger.info("HL7 payload extracted:\n%s", result.hl7_payload.replace("\r", "\n"))

    # Optionally forward to Service Bus.
    if _sb_sender and result.hl7_payload and not result.is_fault_requested:
        _forward_to_service_bus(result.hl7_payload, result.message_control_id)

    # Build and return the appropriate SOAP response.
    if result.is_fault_requested:
        logger.warning("Returning SOAP fault — 'fail' detected in request body.")
        body, content_type = build_fault_response(
            "Message rejected by mock receiver — 'fail' trigger detected.",
            soap_version=result.soap_version,
        )
        return Response(content=body, status_code=500, media_type=content_type)

    body, content_type = build_ack_response(
        result.message_control_id,
        soap_version=result.soap_version,
    )
    logger.info("Returning SOAP ACK — control_id=%s", result.message_control_id)
    return Response(content=body, status_code=200, media_type=content_type)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:  # noqa: ARG001
    """Return a JSON error for unexpected failures rather than a bare 500."""
    logger.exception("Unhandled exception in HTTP Mock Receiver")
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {type(exc).__name__}: {exc}"},
    )


def _forward_to_service_bus(hl7_payload: str, message_control_id: str) -> None:
    """Forward the HL7 payload to the configured Service Bus queue.

    Failures are logged but never propagated — the SOAP response is always
    determined by the message content, not by Service Bus availability.
    """
    try:
        _sb_sender.send_text_message(hl7_payload)  # type: ignore[union-attr]
        logger.info("Message %s forwarded to Service Bus.", message_control_id)
    except Exception as exc:
        logger.error("Failed to forward message %s to Service Bus: %s", message_control_id, exc)
