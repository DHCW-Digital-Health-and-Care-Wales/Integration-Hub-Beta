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
from ultra7.models import Endpoint, Message, MllpMode, Project
from ultra7.senders import get_sender
from ultra7.senders.base import SendResult
from ultra7.senders.mllp_sender import MllpSender, MllpStreamSession

# Queue item: (message_name, SendResult) for a completed send, (info_text, None) for a
# plain informational line, or (None, None) as a sentinel for "job finished".
_ResultItem = tuple[str | None, SendResult | None]

_SEND_MODE_LABELS: dict[MllpMode, str] = {
    "per_message": "Per message",
    "stream": "Stream (1 TCP)",
    "pipelined": "Pipelined burst",
}
_LABEL_TO_SEND_MODE: dict[str, MllpMode] = {label: mode for mode, label in _SEND_MODE_LABELS.items()}


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
        on_mllp_mode_change: Callable[[MllpMode], None] | None = None,
        on_unconfigured_endpoint: Callable[[], bool] | None = None,
    ) -> None:
        super().__init__(parent)
        self._get_endpoint = get_endpoint
        self._get_messages = get_messages
        self._get_selected_messages = get_selected_messages
        self._on_result = on_result
        self._on_info = on_info
        self._on_change = on_change
        self._on_mllp_mode_change = on_mllp_mode_change
        self._on_unconfigured_endpoint = on_unconfigured_endpoint
        self._queue: queue.Queue[_ResultItem] = queue.Queue()
        self._cancel_event = threading.Event()
        self._worker: threading.Thread | None = None
        self._project_enabled = True
        self._is_mllp_endpoint = True

        # Visual grouping frame with clean padding.
        container = ttk.Frame(self)
        container.pack(fill=tk.X, padx=8, pady=(6, 4))

        controls_row = ttk.Frame(container)
        controls_row.pack(fill=tk.X)

        ttk.Label(controls_row, text="Repeat", style="Muted.TLabel").pack(side=tk.LEFT, padx=(0, 6))
        self._repeat_var = tk.StringVar(value="1")
        self._repeat_entry = ttk.Entry(controls_row, textvariable=self._repeat_var, width=6)
        self._repeat_entry.pack(side=tk.LEFT, padx=(0, 12))
        self._repeat_entry.bind("<KeyRelease>", self._handle_setting_change)

        ttk.Label(controls_row, text="Delay (ms)", style="Muted.TLabel").pack(side=tk.LEFT, padx=(0, 6))
        self._delay_var = tk.StringVar(value="0")
        self._delay_entry = ttk.Entry(controls_row, textvariable=self._delay_var, width=7)
        self._delay_entry.pack(side=tk.LEFT, padx=(0, 14))
        self._delay_entry.bind("<KeyRelease>", self._handle_setting_change)

        self._mllp_mode_label = ttk.Label(controls_row, text="MLLP", style="Muted.TLabel")
        self._mllp_mode_label.pack(side=tk.LEFT, padx=(0, 6))
        self._mllp_mode_var = tk.StringVar(value=_SEND_MODE_LABELS["per_message"])
        self._mllp_mode_combo = ttk.Combobox(
            controls_row,
            textvariable=self._mllp_mode_var,
            values=tuple(_SEND_MODE_LABELS.values()),
            state="readonly",
            width=15,
        )
        self._mllp_mode_combo.pack(side=tk.LEFT, padx=(0, 14))
        self._mllp_mode_combo.bind("<<ComboboxSelected>>", self._handle_mllp_mode_change)

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

    def _handle_mllp_mode_change(self, _event: tk.Event | None = None) -> None:
        mode = _LABEL_TO_SEND_MODE.get(self._mllp_mode_var.get(), "per_message")
        if self._on_mllp_mode_change is not None:
            self._on_mllp_mode_change(mode)
        if self._on_change is not None:
            self._on_change()

    def sync_endpoint(self, endpoint: Endpoint) -> None:
        """Sync the inline MLLP stream mode selector with the active project's endpoint."""
        self._is_mllp_endpoint = endpoint.kind == "mllp"
        self._mllp_mode_var.set(_SEND_MODE_LABELS.get(endpoint.mllp_mode, _SEND_MODE_LABELS["per_message"]))
        if self._project_enabled and self._worker is None:
            self._mllp_mode_combo.configure(state="readonly" if self._is_mllp_endpoint else "disabled")

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
        self._mllp_mode_combo.configure(state="readonly" if (enabled and self._is_mllp_endpoint) else "disabled")
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

    def _ensure_configured_endpoint(self) -> Endpoint | None:
        endpoint = self._get_endpoint()
        if endpoint.is_configured:
            return endpoint
        if self._on_unconfigured_endpoint is not None and self._on_unconfigured_endpoint():
            endpoint = self._get_endpoint()
            if endpoint.is_configured:
                return endpoint
        self._status_var.set("Configure an endpoint first")
        return None

    def _start_send(self) -> None:
        if self._worker is not None:
            return
        messages = [m for m in self._get_messages() if m.enabled]
        if not messages:
            self._status_var.set("No enabled messages to send")
            return
        endpoint = self._ensure_configured_endpoint()
        if endpoint is None:
            return
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
        endpoint = self._ensure_configured_endpoint()
        if endpoint is None:
            return

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

        if endpoint.kind == "mllp" and isinstance(sender, MllpSender) and endpoint.mllp_mode != "per_message":
            if endpoint.mllp_mode == "pipelined":
                return self._send_mllp_pipelined(
                    sender, endpoint, messages, repeat_count, destination, label_prefix
                )
            return self._send_mllp_stream(
                sender, endpoint, messages, repeat_count, delay_ms, destination, label_prefix
            )

        for repeat_index in range(repeat_count):
            for message in messages:
                if self._cancel_event.is_set():
                    return False
                outgoing = self._prepare_outgoing(message, repeat_index)
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

    def _prepare_outgoing(self, message: Message, repeat_index: int) -> Message:
        specs = message.all_iterations()
        if not specs:
            return message
        content = apply_iterations(message.content, specs, repeat_index)
        return replace(message, content=content)

    def _send_mllp_stream(
        self,
        sender: MllpSender,
        endpoint: Endpoint,
        messages: list[Message],
        repeat_count: int,
        delay_ms: int,
        destination: str,
        label_prefix: str,
    ) -> bool:
        """Send all frames sequentially over a single persistent MLLP TCP connection."""
        session: MllpStreamSession = sender.open_stream(endpoint)
        self._queue.put((f"Opening persistent MLLP stream to {destination}", None))
        try:
            for repeat_index in range(repeat_count):
                for message in messages:
                    if self._cancel_event.is_set():
                        return False
                    outgoing = self._prepare_outgoing(message, repeat_index)
                    label = f"{label_prefix}{message.name} [{repeat_index + 1}/{repeat_count}]"
                    self._queue.put((f"Streaming {label} on persistent connection to {destination}", None))
                    try:
                        result = session.send_message(outgoing)
                    except Exception as exc:  # noqa: BLE001
                        result = SendResult(ok=False, latency_ms=0.0, response_summary="", error=str(exc))
                    self._queue.put((label, result))
                    if delay_ms and self._cancel_event.wait(delay_ms / 1000):
                        return False
            return True
        finally:
            session.close()
            self._queue.put((f"Closed MLLP stream to {destination}", None))

    def _send_mllp_pipelined(
        self,
        sender: MllpSender,
        endpoint: Endpoint,
        messages: list[Message],
        repeat_count: int,
        destination: str,
        label_prefix: str,
    ) -> bool:
        """Write all MLLP frames back-to-back onto a single TCP stream, then drain all ACKs."""
        planned: list[tuple[str, Message]] = []
        for repeat_index in range(repeat_count):
            for message in messages:
                if self._cancel_event.is_set():
                    return False
                outgoing = self._prepare_outgoing(message, repeat_index)
                label = f"{label_prefix}{message.name} [{repeat_index + 1}/{repeat_count}]"
                planned.append((label, outgoing))

        if not planned:
            return True

        session: MllpStreamSession = sender.open_stream(endpoint)
        self._queue.put((f"Pipelining {len(planned)} MLLP frame(s) on 1 stream to {destination}", None))
        try:
            try:
                session.connect()
                for _label, outgoing in planned:
                    if self._cancel_event.is_set():
                        return False
                    session.send_frame(outgoing)
            except (OSError, TimeoutError) as exc:
                err = SendResult(ok=False, latency_ms=0.0, response_summary="", error=str(exc))
                self._queue.put((planned[0][0], err))
                return True

            for label, _outgoing in planned:
                if self._cancel_event.is_set():
                    return False
                result = session.read_next_ack()
                self._queue.put((label, result))
            return True
        finally:
            session.close()
            self._queue.put((f"Closed pipelined MLLP stream to {destination}", None))

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
        self._mllp_mode_combo.configure(
            state="disabled" if (running or not self._project_enabled or not self._is_mllp_endpoint) else "readonly"
        )
        self._send_btn.configure(state=send_state)
        self._send_once_btn.configure(state=send_state)
        self._cancel_btn.configure(state="normal" if running else "disabled")
        self._status_var.set(status)
