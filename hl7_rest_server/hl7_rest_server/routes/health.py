from fastapi import APIRouter, Request

from hl7_rest_server.api_constant import ApiConstants

router = APIRouter()


@router.get("/hl7MessageReceiver/ping")
def ping(request: Request) -> dict[str, str]:
    """Liveness probe — returns 200 with no dependency checks."""
    context = getattr(request.app.state, "context", None)
    environment = context.config.environment if context else ApiConstants.APPLICATION_NAME
    return {
        "status": "ok",
        "environment": environment,
        "revision": ApiConstants.REVISION,
        "version": ApiConstants.VERSION,
    }


@router.get("/hl7MessageReceiver/status")
def status(request: Request) -> dict[str, object]:
    """Readiness probe — cheap check that the Service Bus sender is initialised."""
    context = getattr(request.app.state, "context", None)
    sender_initialised = bool(context and context.processor and context.processor.sender_client)
    return {
        "application": ApiConstants.APPLICATION_NAME,
        "version": ApiConstants.VERSION,
        "revision": ApiConstants.REVISION,
        "senderInitialised": sender_initialised,
        "status": 200,
    }
