from fastapi import APIRouter, Request

from hl7_rest_server.api_constant import ApiConstants
import time

from datetime import datetime

router = APIRouter()


@router.get("/hl7MessageReceiver/ping")
def ping(request: Request) -> dict[str, str]:
    """Liveness probe — returns 200 with no dependency checks."""
    client_ip = request.client.host
    context = getattr(request.app.state, "context", None)
    environment = context.config.environment if context else ApiConstants.APPLICATION_NAME
    return {
        "environment": environment,
        "revision": ApiConstants.REVISION,
        "version": ApiConstants.VERSION,
        "clientIp": client_ip,
    }


@router.get("/hl7MessageReceiver/status")
def status(request: Request) -> dict[str, object]:
    """Readiness probe — cheap check that the Service Bus sender is initialised."""
    # Start timing
    start_time = time.perf_counter()

    # Execute health check
    ping(request)

    # Previous request time
    last_requested = (
        getattr(request.app.state, "_last_requested", None).isoformat()
        if getattr(request.app.state, "_last_requested", None) is not None
        else "Never"
    )

    # Update request timestamp
    request.app.state._last_requested = datetime.now()

    timeout_threshold = 100 # milliseconds

    response_time = round((time.perf_counter() - start_time) * 1000)

    timeout_occurred = response_time > timeout_threshold

    if not timeout_occurred:
        request.app.state._last_healthy = datetime.now()

        last_healthy = (
            getattr(request.app.state, "_last_healthy", None).isoformat()
            if getattr(request.app.state, "_last_healthy", None) is not None
            else "Never"
        )

    description = (f"Version {ApiConstants.VERSION}.{ApiConstants.REVISION} API is working, response time {response_time} ms")
    return {
        "application": ApiConstants.APPLICATION_NAME,
        "description": description,
        "status": 200,
        "timeout": timeout_occurred,
        "lastRequested": last_requested,
        "lastHealthy": last_healthy,
        "version": ApiConstants.VERSION,
        "revision": ApiConstants.REVISION,
    }
