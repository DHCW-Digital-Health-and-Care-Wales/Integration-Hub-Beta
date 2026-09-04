import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from hl7_rest_server.errors import Hl7ParseError, Hl7ValidationError
from hl7_rest_server.message_input_adapter import to_er7
from hl7_rest_server.models import HL7Message

logger = logging.getLogger(__name__)

router = APIRouter()


def _error_envelope(status_code: int, error_message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"StatusCode": status_code, "ErrorMessage": error_message})


@router.post("/hl7MessageReceiver", response_model=None)
def receive_hl7_message(payload: HL7Message, request: Request) -> PlainTextResponse | JSONResponse:
    """Accept an HL7 message (ER7 or HL7 v2 XML), enqueue it, and return an ACK/NACK.

    Routes are defined synchronously (``def``) so FastAPI runs them in the
    threadpool per request. The Service Bus send happens synchronously inside the
    handler and the 201 ACK is only returned once it completes.
    """
    context = request.app.state.context
    config = context.config

    content = payload.messageContent
    if len(content.encode("utf-8")) > config.max_message_size_bytes:
        logger.warning("Rejected oversize message (limit: %s bytes)", config.max_message_size_bytes)
        return _error_envelope(400, "Message exceeds the maximum allowed size.")

    # Line-ending normalisation (§6.3) then XML→ER7 adaptation (§6.4).
    normalised = content.replace("\r\n", "\r").replace("\n", "\r")
    try:
        er7_message = to_er7(normalised)
    except Exception as e:  # Malformed XML / unable to convert to ER7 → treated as unparsable.
        logger.error("Failed to convert inbound message to ER7: %s", e)
        nack = context.ack_builder.build_generic_nack(f"{e}")
        return _error_envelope(500, nack)

    try:
        ack_message = context.processor.process(er7_message)
        return PlainTextResponse(content=ack_message, status_code=201)
    except Hl7ValidationError as e:
        logger.info("Message validation failed: %s", e.reason)
        return _error_envelope(422, e.nack_message)
    except Hl7ParseError as e:
        nack = context.ack_builder.build_generic_nack(f"{e.reason}")
        return _error_envelope(500, nack)
    except Exception as e:  # e.g. Service Bus send failure — no ACK is returned.
        logger.exception("Unexpected error while processing message: %s", e)
        nack = context.ack_builder.build_generic_nack(f"{e}")
        return _error_envelope(500, nack)
