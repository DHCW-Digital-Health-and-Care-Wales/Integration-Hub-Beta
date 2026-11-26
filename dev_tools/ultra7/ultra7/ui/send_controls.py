"""Repeat count / delay controls and manual sending, run off the UI thread."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from dataclasses import replace
from tkinter import ttk
from typing import Callable
from urllib.parse import urlparse

from ultra7.iteration import apply_iterations
from ultra7.models import Endpoint, Message, Project
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
        on_change: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._get_endpoint = get_endpoint
        self._get_messages = get_messages
        self._get_selected_messages = get_selected_messages
        self._on_result = on_result
        self._on_info = on_info
        self._on_change = on_change
        self._queue: queue.Queue[_ResultItem] = queue.Queue()
        self._cancel_event = threading.Event()
        self._worker: threading.Thread | None = None
        self._project_enabled = True

        # Visual grouping frame with clean padding.
        container = ttk.Frame(self)
        container.pack(fill=tk.X, padx=8, pady=(6, 4))

        controls_row = ttk.Frame(container)
        controls_row.pack(fill=tk.X)

        ttk.Label(controls_row, text="Repeat", style="Muted.TLabel").pack(side=tk.LEFT, padx=(0, 6))
        self._repeat_var = tk.StringVar(value="1")
        self._repeat_entry = ttk.Entry(controls_row, textvariable=self._repeat_var, width=6)
        self._repeat_entry.pack(side=tk.LEFT, padx=(0, 14))
        self._repeat_entry.bind("<KeyRelease>", self._handle_setting_change)

        ttk.Label(controls_row, text="Delay (ms)", style="Muted.TLabel").pack(side=tk.LEFT, padx=(0, 6))
        self._delay_var = tk.StringVar(value="0")
        self._delay_entry = ttk.Entry(controls_row, textvariable=self._delay_var, width=8)
        self._delay_entry.pack(side=tk.LEFT, padx=(0, 18))
        self._delay_entry.bind("<KeyRelease>", self._handle_setting_change)

        self._send_btn = ttk.Button(controls_row, text="▶ Send", style="Accent.TButton", command=self._start_send)
        self._send_btn.pack(side=tk.LEFT, padx=(0, 6))
        self._send_once_btn = ttk.Button(controls_row, text="Send Selected Once", command=self._start_send_once)
        self._send_once_btn.pack(side=tk.LEFT, padx=(0, 6))
        self._cancel_btn = ttk.Button(
            controls_row, text="■ Cancel", style="Danger.TButton", command=self._cancel, state="disabled"
        )
        self._cancel_btn.pack(side=tk.LEFT, padx=(0, 6))

        self._status_var = tk.StringVar(value="")
        ttk.Label(controls_row, textvariable=self._status_var, style="Muted.TLabel").pack(side=tk.LEFT, padx=10)

    def _handle_setting_change(self, _event: tk.Event) -> None:
        if self._on_change is not None:
            self._on_change()

    def set_repeat_and_delay(self, repeat_count: int, delay_ms: int) -> None:
        self._repeat_var.set(str(repeat_count))
        self._delay_var.set(str(delay_ms))

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable project send controls (entries and send buttons)."""
        self._project_enabled = enabled
        if self._worker is not None:
            return
        state = "normal" if enabled else "disabled"
        for widget in (
            self._repeat_entry,
            self._delay_entry,
            self._send_btn,
            self._send_once_btn,
        ):
            widget.configure(state=state)
        self._cancel_btn.configure(state="disabled")

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

    def start_batch(self, projects: list[Project]) -> bool:
        """Run multiple projects sequentially off the UI thread. Returns False if busy."""
        if self._worker is not None:
            return False
        self._cancel_event = threading.Event()
        self._set_running(True, "Running batch…")
        self._worker = threading.Thread(
            target=self._batch_send_worker, args=(projects,), daemon=True
        )
        self._worker.start()
        self.after(100, self._poll_queue)
        return True

    def _send_messages_loop(
        self,
        endpoint: Endpoint,
        messages: list[Message],
        repeat_count: int,
        delay_ms: int,
        label_prefix: str = "",
    ) -> bool:
        """Send *messages* for *repeat_count* iterations. Returns False if cancelled."""
        sender = get_sender(endpoint.kind)
        destination = _describe_destination(endpoint)
        for repeat_index in range(repeat_count):
            for message in messages:
                if self._cancel_event.is_set():
                    return False
                outgoing = message
                specs = message.all_iterations()
                if specs:
                    content = apply_iterations(message.content, specs, repeat_index)
                    outgoing = replace(message, content=content)
                label = f"{label_prefix}{message.name} [{repeat_index + 1}/{repeat_count}]"
                self._queue.put((f"Sending {label} to {destination}", None))
                try:
                    result = sender.send(endpoint, outgoing)
                except Exception as exc:  # noqa: BLE001 — always surface send failures to the log
                    result = SendResult(ok=False, latency_ms=0.0, response_summary="", error=str(exc))
                self._queue.put((label, result))
                if delay_ms and self._cancel_event.wait(delay_ms / 1000):
                    return False
        return True

    def _send_worker(
        self, endpoint: Endpoint, messages: list[Message], repeat_count: int, delay_ms: int
    ) -> None:
        try:
            self._send_messages_loop(endpoint, messages, repeat_count, delay_ms)
        finally:
            self._queue.put((None, None))

    def _batch_send_worker(self, projects: list[Project]) -> None:
        try:
            for project in projects:
                if self._cancel_event.is_set():
                    return
                self._queue.put((f"=== Running: {project.name} ===", None))
                messages = [m for m in project.messages if m.enabled]
                if not messages:
                    self._queue.put(("No enabled messages", None))
                    continue
                try:
                    completed = self._send_messages_loop(
                        project.endpoint, messages, project.repeat_count, project.delay_ms, label_prefix="  "
                    )
                except ValueError as exc:
                    self._queue.put((str(exc), None))
                    continue
                if not completed:
                    return
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
                    status = "Cancelled" if self._cancel_event.is_set() else "Done"
                    self._worker = None
                    self._set_running(False, status)
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
        send_state = "disabled" if running or not self._project_enabled else "normal"
        entry_state = "normal" if self._project_enabled else "disabled"
        self._repeat_entry.configure(state=entry_state)
        self._delay_entry.configure(state=entry_state)
        self._send_btn.configure(state=send_state)
        self._send_once_btn.configure(state=send_state)
        self._cancel_btn.configure(state="normal" if running else "disabled")
        self._status_var.set(status)
