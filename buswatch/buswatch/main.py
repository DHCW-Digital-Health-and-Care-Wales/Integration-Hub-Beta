"""FastAPI web app for browsing Azure Service Bus emulator messages."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

try:
    # Normal import path when the package is installed or executed from project root.
    from buswatch.config import Settings, get_settings
    from buswatch.servicebus_reader import MessageDetail, MessageSummary, QueueRuntime, ServiceBusReader  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover - supports running from package directory
    # Fallback path to support direct execution from buswatch/buswatch/.
    from config import Settings, get_settings  # type: ignore[import-not-found, no-redef]
    from servicebus_reader import (  # type: ignore[import-not-found, no-redef]
        MessageDetail,
        MessageSummary,
        ServiceBusReader,
    )


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Global singletons keep setup simple for this lightweight app:
# - settings: immutable runtime configuration
# - reader: shared Service Bus client wrapper
# - queue_cache: per-queue snapshots rendered on the index page
settings: Settings = get_settings()
reader = ServiceBusReader(settings.servicebus_connection_string)
queue_cache: dict[str, dict[str, object]] = {}
queue_cache_lock = Lock()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:  # noqa: ARG001
    # FastAPI lifespan hook ensures we close AMQP resources cleanly on shutdown.
    yield
    reader.close()


app = FastAPI(title="BusWatch", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    """Render queue snapshots for the BusWatch home page.

    Behavior summary:
    - Resolve queue names from config override or emulator config file.
    - Refresh only missing queues plus optionally one queue requested by user.
    - If refresh_all=true, refresh all queues regardless of cache state.
    - Render cached snapshots for all queues so the page stays responsive.
    """
    error_message: str | None = None
    refresh_queue = request.query_params.get("refresh_queue")
    refresh_all = request.query_params.get("refresh_all") == "true"
    cleared_queue = request.query_params.get("cleared_queue")
    cleared_count = request.query_params.get("cleared_count")
    clear_error = request.query_params.get("clear_error")

    action_message: str | None = None
    action_error: str | None = None
    if cleared_queue and cleared_count is not None:
        action_message = f"Cleared {cleared_count} message(s) from queue '{cleared_queue}'."
    if cleared_queue and clear_error:
        action_error = f"Unable to clear queue '{cleared_queue}': {clear_error}"

    try:
        queue_names = settings.queue_names or reader.list_queues()
    except Exception as exc:  # pragma: no cover - depends on local emulator state
        # Keep the page renderable even if queue discovery fails.
        queue_names = []
        error_message = str(exc)

    def _fetch_queue(queue_name: str) -> dict[str, object]:
        """Build one queue snapshot used by the index template."""
        queue_errors: list[str] = []
        messages: list[MessageSummary] = []

        try:
            messages = reader.peek_messages(queue_name, settings.peek_count)
        except Exception as exc:  # pragma: no cover - depends on queue permissions and namespace state
            # Surface per-queue errors inline while preserving the rest of the page.
            queue_errors.append(f"Message peek failed: {exc}")

        queue_error = " | ".join(queue_errors) if queue_errors else None
        runtime = reader.get_queue_runtime(queue_name)
        return {
            "name": queue_name,
            "runtime": runtime,
            "messages": messages,
            "error": queue_error,
            "refreshed_at": datetime.now(UTC).strftime("%H:%M:%S UTC"),
        }

    with queue_cache_lock:
        # Cache keys track which queues already have a snapshot.
        cached_names = set(queue_cache.keys())

    if refresh_all:
        # Refresh all queues when user clicks "Refresh All Queues" button.
        queues_to_refresh = list(queue_names)
    else:
        missing_queues = [name for name in queue_names if name not in cached_names]
        queues_to_refresh = list(missing_queues)

        if refresh_queue and refresh_queue in queue_names and refresh_queue not in queues_to_refresh:
            # A targeted refresh is user-triggered from "Refresh Queue" button.
            queues_to_refresh.append(refresh_queue)

    if queues_to_refresh:
        # Refreshes are parallelized to reduce end-to-end page latency when many
        # queues are loaded for the first time.
        with ThreadPoolExecutor(max_workers=min(len(queues_to_refresh), 10)) as pool:
            future_to_queue = {pool.submit(_fetch_queue, name): name for name in queues_to_refresh}
            for future in as_completed(future_to_queue):
                queue_name = future_to_queue[future]
                try:
                    snapshot = future.result()
                except Exception as exc:  # pragma: no cover
                    # Defensive fallback in case worker-level failures occur.
                    snapshot = {
                        "name": queue_name,
                        "runtime": reader.get_queue_runtime(queue_name),
                        "messages": [],
                        "error": str(exc),
                        "refreshed_at": datetime.now(UTC).strftime("%H:%M:%S UTC"),
                    }

                with queue_cache_lock:
                    queue_cache[queue_name] = snapshot

    with queue_cache_lock:
        # Preserve queue ordering from queue_names while rendering cached content.
        queues = [
            queue_cache.get(
                queue_name,
                {
                    "name": queue_name,
                    "runtime": reader.get_queue_runtime(queue_name),
                    "messages": [],
                    "error": "Queue not yet loaded",
                    "refreshed_at": "-",
                },
            )
            for queue_name in queue_names
        ]

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "queues": queues,
            "peek_count": settings.peek_count,
            "error_message": error_message,
            "action_message": action_message,
            "action_error": action_error,
        },
    )


@app.post("/queues/{queue_name}/clear")
def clear_queue(queue_name: str) -> RedirectResponse:
    """Clear all currently available messages from one queue and redirect home."""
    with queue_cache_lock:
        queue_cache.pop(queue_name, None)

    try:
        cleared_count = reader.clear_queue(queue_name)
        query = urlencode(
            {
                "refresh_queue": queue_name,
                "cleared_queue": queue_name,
                "cleared_count": str(cleared_count),
            }
        )
    except Exception as exc:  # pragma: no cover - depends on local emulator state
        query = urlencode(
            {
                "refresh_queue": queue_name,
                "cleared_queue": queue_name,
                "clear_error": str(exc),
            }
        )

    return RedirectResponse(url=f"/?{query}", status_code=303)


@app.get("/queues/{queue_name}/messages/{sequence_number}", response_class=HTMLResponse)
def message_detail(request: Request, queue_name: str, sequence_number: int) -> HTMLResponse:
    """Render detailed view for a specific message sequence number."""
    try:
        detail: MessageDetail | None = reader.get_message_detail(
            queue_name=queue_name,
            sequence_number=sequence_number,
            search_limit=settings.detail_search_limit,
        )
    except Exception as exc:  # pragma: no cover - depends on local emulator state
        # Map broker/transport errors to gateway-style HTTP failure.
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if detail is None:
        # Not-found keeps UX clear when sequence is outside peek search window.
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
