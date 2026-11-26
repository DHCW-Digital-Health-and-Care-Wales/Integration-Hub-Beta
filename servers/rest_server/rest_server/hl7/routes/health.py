import time
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from rest_server.hl7.api_constant import ApiConstants

router = APIRouter()


@router.get("/hl7MessageReceiver/ping")
def ping(request: Request) -> dict[str, str]:
    """Liveness probe — returns 200 with no dependency checks."""
    client_ip = request.client.host if request.client else ""
    context = getattr(request.app.state, "context", None)
    environment = context.config.environment if context else ApiConstants.APPLICATION_NAME
    return {
        "environment": environment,
        "revision": ApiConstants.REVISION,
        "version": ApiConstants.VERSION,
        "clientIp": client_ip,
    }


@router.get("/hl7MessageReceiver/status", response_model=None)
def status(request: Request) -> dict[str, object] | JSONResponse:
    """Readiness probe — verifies the runtime context and Service Bus sender are initialised."""
    start_time = time.perf_counter()

    context = getattr(request.app.state, "context", None)
    processor = getattr(context, "processor", None)
    sender_client = getattr(processor, "sender_client", None)
    if context is None or processor is None or sender_client is None:
        return JSONResponse(
            status_code=503,
            content={
                "application": ApiConstants.APPLICATION_NAME,
                "description": "Service Bus sender is not initialised",
                "status": 503,
                "timeout": False,
                "version": ApiConstants.VERSION,
                "revision": ApiConstants.REVISION,
            },
        )

    ping(request)

    previous_requested_at = getattr(request.app.state, "_last_requested", None)
    last_requested = previous_requested_at.isoformat() if previous_requested_at is not None else "Never"
    request.app.state._last_requested = datetime.now()

    timeout_threshold = 100  # milliseconds
    response_time = round((time.perf_counter() - start_time) * 1000)
    timeout_occurred = response_time > timeout_threshold

    previous_healthy_at = getattr(request.app.state, "_last_healthy", None)
    last_healthy = previous_healthy_at.isoformat() if previous_healthy_at is not None else "Never"

    if not timeout_occurred:
        request.app.state._last_healthy = datetime.now()
        last_healthy = request.app.state._last_healthy.isoformat()

    description = (
        f"Version {ApiConstants.VERSION}.{ApiConstants.REVISION} API is working, response time {response_time} ms"
    )
    payload: dict[str, object] = {
        "application": ApiConstants.APPLICATION_NAME,
        "description": description,
        "status": 503 if timeout_occurred else 200,
        "timeout": timeout_occurred,
        "lastRequested": last_requested,
        "lastHealthy": last_healthy,
        "version": ApiConstants.VERSION,
        "revision": ApiConstants.REVISION,
    }
    if timeout_occurred:
        return JSONResponse(status_code=503, content=payload)
    return payload
