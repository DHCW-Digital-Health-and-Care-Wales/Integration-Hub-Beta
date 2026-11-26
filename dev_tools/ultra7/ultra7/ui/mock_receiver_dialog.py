"""Non-modal tool window for Ultra7's built-in local Mock MLLP / HTTP Receiver."""
from __future__ import annotations

import queue
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable

from ultra7.formats.highlighting import configure_tags, highlight
from ultra7.mock_receiver import MockHttpServer, MockMllpServer, ReceivedMessage
from ultra7.models import Message
from ultra7.ui.themes import DEFAULT_THEME_NAME, Theme, get_border_color, get_semantic_colors, get_theme


class MockReceiverDialog(tk.Toplevel):
    """Interactive local MLLP/HTTP listener window with live capture and project import."""

    def __init__(
        self,
        parent: tk.Misc,
        on_import_message: Callable[[Message], None],
        theme: Theme | None = None,
    ) -> None:
        super().__init__(parent)
        self.title("Ultra7 — Mock Receiver")
        self.geometry("880x580")
        self._on_import_message = on_import_message
        self._theme = theme or get_theme(DEFAULT_THEME_NAME)
        self.configure(bg=self._theme.bg)

        self._server: MockMllpServer | MockHttpServer | None = None
        self._incoming: queue.Queue[ReceivedMessage] = queue.Queue()
        self._captured: list[ReceivedMessage] = []

        # Config bar
        cfg = ttk.Frame(self)
        cfg.pack(fill=tk.X, padx=12, pady=(10, 6))

        ttk.Label(cfg, text="Protocol", style="Muted.TLabel").pack(side=tk.LEFT)
        self._proto_var = tk.StringVar(value="mllp")
        ttk.OptionMenu(
            cfg, self._proto_var, "mllp", "mllp", "http", command=self._on_proto_change  # type: ignore[arg-type]
        ).pack(side=tk.LEFT, padx=(6, 12))

        ttk.Label(cfg, text="Host", style="Muted.TLabel").pack(side=tk.LEFT)
        self._host_var = tk.StringVar(value="127.0.0.1")
        ttk.Entry(cfg, textvariable=self._host_var, width=12).pack(side=tk.LEFT, padx=(6, 10))

        ttk.Label(cfg, text="Port", style="Muted.TLabel").pack(side=tk.LEFT)
        self._port_var = tk.StringVar(value="2599")
        ttk.Entry(cfg, textvariable=self._port_var, width=7).pack(side=tk.LEFT, padx=(6, 10))

        ttk.Label(cfg, text="Delay (ms)", style="Muted.TLabel").pack(side=tk.LEFT)
        self._delay_var = tk.StringVar(value="0")
        ttk.Entry(cfg, textvariable=self._delay_var, width=6).pack(side=tk.LEFT, padx=(6, 12))

        self._toggle_btn = ttk.Button(cfg, text="▶ Start", style="Accent.TButton", command=self._toggle_server)
        self._toggle_btn.pack(side=tk.LEFT, padx=(0, 8))

        self._status_var = tk.StringVar(value="Stopped")
        self._status_label = ttk.Label(cfg, textvariable=self._status_var, style="Muted.TLabel")
        self._status_label.pack(side=tk.LEFT)

        # Response config bar
        resp = ttk.Frame(self)
        resp.pack(fill=tk.X, padx=12, pady=(0, 8))
        ttk.Label(resp, text="MLLP ACK", style="Muted.TLabel").pack(side=tk.LEFT)
        self._ack_var = tk.StringVar(value="AA")
        self._ack_menu = ttk.OptionMenu(resp, self._ack_var, "AA", "AA", "CA", "AE", "AR")
        self._ack_menu.pack(side=tk.LEFT, padx=(6, 14))

        ttk.Label(resp, text="HTTP Status", style="Muted.TLabel").pack(side=tk.LEFT)
        self._http_status_var = tk.StringVar(value="200")
        self._http_status_entry = ttk.Entry(resp, textvariable=self._http_status_var, width=5)
        self._http_status_entry.pack(side=tk.LEFT, padx=(6, 10))

        ttk.Label(resp, text="HTTP Body", style="Muted.TLabel").pack(side=tk.LEFT)
        self._http_body_var = tk.StringVar(value='{"status": "ok"}')
        self._http_body_entry = ttk.Entry(resp, textvariable=self._http_body_var, width=32)
        self._http_body_entry.pack(side=tk.LEFT, padx=(6, 0), fill=tk.X, expand=True)

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=12, pady=(0, 8))

        # Split capture list + preview
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 8))

        left = ttk.Frame(paned)
        paned.add(left, weight=0)
        ttk.Label(left, text="RECEIVED MESSAGES", style="Section.TLabel").pack(anchor="w", pady=(0, 4))
        border = get_border_color(self._theme)
        self.listbox = tk.Listbox(
            left,
            width=30,
            font=("Rubik", 9),
            bd=0,
            highlightthickness=1,
            bg=self._theme.pane_bg,
            fg=self._theme.pane_fg,
            selectbackground=self._theme.select_bg,
            selectforeground=self._theme.select_fg,
            highlightbackground=border,
            highlightcolor=self._theme.accent,
        )
        self.listbox.pack(fill=tk.BOTH, expand=True)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        left_btns = ttk.Frame(left)
        left_btns.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(left_btns, text="Import to Project", command=self._import_selected).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(left_btns, text="Clear", style="Subtle.TButton", command=self._clear).pack(side=tk.RIGHT)

        right = ttk.Frame(paned)
        paned.add(right, weight=1)
        ttk.Label(right, text="PAYLOAD", style="Section.TLabel").pack(anchor="w", padx=(6, 0), pady=(0, 4))
        self.preview_text = tk.Text(
            right,
            wrap="none",
            font=("Menlo", 10),
            bd=0,
            padx=8,
            pady=8,
            highlightthickness=1,
            bg=self._theme.pane_bg,
            fg=self._theme.pane_fg,
            selectbackground=self._theme.select_bg,
            selectforeground=self._theme.select_fg,
            highlightbackground=border,
            highlightcolor=self._theme.accent,
        )
        self.preview_text.pack(fill=tk.BOTH, expand=True, padx=(6, 0))
        configure_tags(self.preview_text, self._theme)
        self.preview_text.configure(state="disabled")

        self._on_proto_change("mllp")
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(150, self._poll_incoming)

    def _on_proto_change(self, proto: str) -> None:
        is_mllp = proto == "mllp"
        self._port_var.set("2599" if is_mllp else "8090")
        self._ack_menu.configure(state="normal" if is_mllp else "disabled")
        http_state = "disabled" if is_mllp else "normal"
        self._http_status_entry.configure(state=http_state)
        self._http_body_entry.configure(state=http_state)

    def _toggle_server(self) -> None:
        if self._server is not None:
            self.stop_server()
            return
        host = self._host_var.get().strip() or "127.0.0.1"
        try:
            port = int(self._port_var.get().strip())
        except ValueError:
            messagebox.showerror("Mock Receiver", "Port must be an integer.", parent=self)
            return
        try:
            delay_ms = max(0, int(self._delay_var.get().strip() or "0"))
        except ValueError:
            delay_ms = 0

        proto = self._proto_var.get()
        try:
            if proto == "mllp":
                srv: MockMllpServer | MockHttpServer = MockMllpServer(
                    host,
                    port,
                    ack_code=self._ack_var.get(),
                    delay_ms=delay_ms,
                    on_message=self._incoming.put,
                )
            else:
                try:
                    status = int(self._http_status_var.get().strip() or "200")
                except ValueError:
                    status = 200
                srv = MockHttpServer(
                    host,
                    port,
                    status_code=status,
                    response_body=self._http_body_var.get(),
                    delay_ms=delay_ms,
                    on_message=self._incoming.put,
                )
            bound_port = srv.start()
        except OSError as exc:
            messagebox.showerror("Mock Receiver", f"Could not start listener: {exc}", parent=self)
            return

        self._server = srv
        self._toggle_btn.configure(text="■ Stop", style="Danger.TButton")
        colors = get_semantic_colors(self._theme)
        self._status_label.configure(foreground=colors["ok"])
        self._status_var.set(f"Listening ({proto.upper()}) on {host}:{bound_port}")

    def stop_server(self) -> None:
        if self._server is not None:
            self._server.stop()
            self._server = None
        self._toggle_btn.configure(text="▶ Start", style="Accent.TButton")
        self._status_label.configure(foreground=self._theme.fg)
        self._status_var.set("Stopped")

    def _poll_incoming(self) -> None:
        try:
            while True:
                msg = self._incoming.get_nowait()
                self._captured.append(msg)
                label = f"[{msg.timestamp}] {msg.protocol.upper()} from {msg.remote}"
                self.listbox.insert(tk.END, label)
                self.listbox.see(tk.END)
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(150, self._poll_incoming)

    def _on_select(self, _event: tk.Event) -> None:
        sel = self.listbox.curselection()
        if not sel:
            return
        msg = self._captured[sel[0]]
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", tk.END)
        self.preview_text.insert("1.0", msg.content)
        highlight(self.preview_text, msg.detected_format)
        self.preview_text.configure(state="disabled")

    def _import_selected(self) -> None:
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showinfo("Mock Receiver", "Select a received message first.", parent=self)
            return
        msg = self._captured[sel[0]]
        self._on_import_message(
            Message(
                name=f"Captured {msg.timestamp}",
                format=msg.detected_format,
                content=msg.content,
            )
        )

    def _clear(self) -> None:
        self._captured.clear()
        self.listbox.delete(0, tk.END)
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", tk.END)
        self.preview_text.configure(state="disabled")

    def _on_close(self) -> None:
        self.stop_server()
        self.destroy()
