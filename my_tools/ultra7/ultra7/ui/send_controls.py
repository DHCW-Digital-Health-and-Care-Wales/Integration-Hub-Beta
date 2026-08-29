"""Repeat count / delay controls and manual sending, run off the UI thread."""
from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from dataclasses import replace
from tkinter import ttk
from typing import Callable
from urllib.parse import urlparse

from ultra7.iteration import apply_iteration
from ultra7.models import Endpoint, Message
from ultra7.senders import get_sender
from ultra7.senders.base import SendResult

# Queue item: (message_name, SendResult) for a completed send, (info_text, None) for a
# plain informational line, or (None, None) as a sentinel for "job finished".
_ResultItem = tuple[str | None, SendResult | None]


def _describe_destination(endpoint: Endpoint) -> str:
    if endpoint.kind == "mllp":
        return f"{endpoint.host} on port {endpoint.port}"
    parsed = urlparse(endpoint.url)
    host = parsed.hostname or endpoint.url
    if parsed.port:
        return f"{host} on port {parsed.port}"
    return host


class SendControls(ttk.Frame):
    """Drives manual repeat-sends off the UI thread."""

    def __init__(
        self,
        parent: tk.Misc,
        get_endpoint: Callable[[], Endpoint],
        get_messages: Callable[[], list[Message]],
        get_selected_messages: Callable[[], list[Message]],
        on_result: Callable[[str, SendResult], None],
        on_info: Callable[[str], None],
    ) -> None:
        super().__init__(parent)
        self._get_endpoint = get_endpoint
        self._get_messages = get_messages
        self._get_selected_messages = get_selected_messages
        self._on_result = on_result
        self._on_info = on_info
        self._queue: queue.Queue[_ResultItem] = queue.Queue()
        self._cancel_event = threading.Event()
        self._worker: threading.Thread | None = None

        ttk.Label(self, text="Repeat count").pack(side=tk.LEFT, padx=(4, 2))
        self._repeat_var = tk.StringVar(value="1")
        ttk.Entry(self, textvariable=self._repeat_var, width=6).pack(side=tk.LEFT, padx=(0, 8))

        ttk.Label(self, text="Delay (ms)").pack(side=tk.LEFT, padx=(4, 2))
        self._delay_var = tk.StringVar(value="0")
        ttk.Entry(self, textvariable=self._delay_var, width=8).pack(side=tk.LEFT, padx=(0, 8))

        self._send_btn = ttk.Button(self, text="Send", command=self._start_send)
        self._send_btn.pack(side=tk.LEFT, padx=4)
        self._send_once_btn = ttk.Button(self, text="Send Selected Once", command=self._start_send_once)
        self._send_once_btn.pack(side=tk.LEFT, padx=4)
        self._cancel_btn = ttk.Button(self, text="Cancel", command=self._cancel, state="disabled")
        self._cancel_btn.pack(side=tk.LEFT, padx=4)

        self._status_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self._status_var).pack(side=tk.LEFT, padx=8)

    def get_repeat_count(self) -> int:
        try:
            return max(1, int(self._repeat_var.get()))
        except ValueError:
            return 1

    def get_delay_ms(self) -> int:
        try:
            return max(0, int(self._delay_var.get()))
        except ValueError:
            return 0

    # -- manual send ---------------------------------------------------------

    def _start_send(self) -> None:
        if self._worker is not None:
            return
        messages = [m for m in self._get_messages() if m.enabled]
        if not messages:
            self._status_var.set("No enabled messages to send")
            return
        endpoint = self._get_endpoint()
        repeat_count = self.get_repeat_count()
        delay_ms = self.get_delay_ms()

        self._cancel_event = threading.Event()
        self._set_running(True, "Sending…")
        self._worker = threading.Thread(
            target=self._send_worker, args=(endpoint, messages, repeat_count, delay_ms), daemon=True
        )
        self._worker.start()
        self.after(100, self._poll_queue)

    def _start_send_once(self) -> None:
        if self._worker is not None:
            return
        messages = self._get_selected_messages()
        if not messages:
            self._status_var.set("No message selected")
            return
        endpoint = self._get_endpoint()

        self._cancel_event = threading.Event()
        self._set_running(True, "Sending…")
        self._worker = threading.Thread(
            target=self._send_worker, args=(endpoint, messages, 1, 0), daemon=True
        )
        self._worker.start()
        self.after(100, self._poll_queue)

    def _send_worker(
        self, endpoint: Endpoint, messages: list[Message], repeat_count: int, delay_ms: int
    ) -> None:
        try:
            sender = get_sender(endpoint.kind)
            destination = _describe_destination(endpoint)
            for repeat_index in range(repeat_count):
                for message in messages:
                    if self._cancel_event.is_set():
                        return
                    outgoing = message
                    if message.iteration is not None:
                        content = apply_iteration(message.content, message.iteration, repeat_index)
                        outgoing = replace(message, content=content)
                    label = f"{message.name} [{repeat_index + 1}/{repeat_count}]"
                    self._queue.put((f"Sending {label} to {destination}", None))
                    try:
                        result = sender.send(endpoint, outgoing)
                    except Exception as exc:  # noqa: BLE001 — always surface send failures to the log
                        result = SendResult(ok=False, latency_ms=0.0, response_summary="", error=str(exc))
                    self._queue.put((label, result))
                    if delay_ms:
                        time.sleep(delay_ms / 1000)
        finally:
            self._queue.put((None, None))

    # -- shared plumbing -------------------------------------------------------

    def _cancel(self) -> None:
        self._cancel_event.set()

    def _poll_queue(self) -> None:
        try:
            while True:
                name, result = self._queue.get_nowait()
                if name is None:
                    self._set_running(False, "Done")
                    self._worker = None
                    return
                if result is None:
                    self._on_info(name)
                else:
                    self._on_result(name, result)
        except queue.Empty:
            pass
        if self._worker is not None:
            self.after(100, self._poll_queue)

    def _set_running(self, running: bool, status: str) -> None:
        self._send_btn.configure(state="disabled" if running else "normal")
        self._send_once_btn.configure(state="disabled" if running else "normal")
        self._cancel_btn.configure(state="normal" if running else "disabled")
        self._status_var.set(status)
