"""FastAPI web app for browsing Azure Service Bus emulator messages."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from buswatch.config import Settings, get_settings
from buswatch.servicebus_reader import MessageDetail, MessageSummary, QueueRuntime, ServiceBusReader


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="BusWatch", version="0.1.0")
settings: Settings = get_settings()
reader = ServiceBusReader(settings.servicebus_connection_string)


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    error_message: str | None = None
    try:
        queue_names = settings.queue_names or reader.list_queues()
    except Exception as exc:  # pragma: no cover - depends on local emulator state
        queue_names = []
        error_message = str(exc)

    queues: list[dict[str, object]] = []
    for queue_name in queue_names:
        try:
            runtime: QueueRuntime = reader.get_queue_runtime(queue_name)
            messages: list[MessageSummary] = reader.peek_messages(queue_name, settings.peek_count)
            queue_error: str | None = None
        except Exception as exc:  # pragma: no cover - depends on queue permissions and namespace state
            runtime = QueueRuntime(
                name=queue_name,
                active_count=None,
                dead_letter_count=None,
                scheduled_count=None,
                transfer_dead_letter_count=None,
            )
            messages = []
            queue_error = str(exc)

        queues.append({"name": queue_name, "runtime": runtime, "messages": messages, "error": queue_error})

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "queues": queues,
            "peek_count": settings.peek_count,
            "error_message": error_message,
        },
    )


@app.get("/queues/{queue_name}/messages/{sequence_number}", response_class=HTMLResponse)
def message_detail(request: Request, queue_name: str, sequence_number: int) -> HTMLResponse:
    try:
        detail: MessageDetail | None = reader.get_message_detail(
            queue_name=queue_name,
            sequence_number=sequence_number,
            search_limit=settings.detail_search_limit,
        )
    except Exception as exc:  # pragma: no cover - depends on local emulator state
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if detail is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Message {sequence_number} not found in queue '{queue_name}'. "
                f"Increase BUSWATCH_DETAIL_SEARCH_LIMIT if needed."
            ),
        )

    return templates.TemplateResponse(
        request=request,
        name="message_detail.html",
        context={"message": detail},
    )
