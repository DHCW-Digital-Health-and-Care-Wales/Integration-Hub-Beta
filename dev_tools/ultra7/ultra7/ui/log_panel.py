"""Togglable bottom panel showing a log of sends, live batch stats, and a response inspector."""
from __future__ import annotations

import math
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime, timezone
from tkinter import filedialog, messagebox, ttk

from ultra7.formats.detect import detect_format
from ultra7.formats.highlighting import configure_tags, highlight
from ultra7.formats.pretty_print import pretty_print
from ultra7.senders.base import SendResult
from ultra7.settings import AppPreferences
from ultra7.ui.themes import DEFAULT_THEME_NAME, Theme, get_border_color, get_semantic_colors, get_theme


@dataclass(frozen=True)
class LoggedEntry:
    """Full record for a single send attempt, backing the Response Inspector."""

    timestamp: str
    label: str
    result: SendResult


class ResponseInspectorDialog(tk.Toplevel):
    """Popup showing the full syntax-highlighted response for a logged send."""

    def __init__(self, parent: tk.Misc, entry: LoggedEntry, theme: Theme) -> None:
        super().__init__(parent)
        self.title(f"Response Inspector — {entry.label}")
        self.geometry("760x480")
        self.transient(parent)  # type: ignore[call-overload]
        self.configure(bg=theme.bg)

        header = ttk.Frame(self)
        header.pack(fill=tk.X, padx=12, pady=(10, 6))
        colors = get_semantic_colors(theme)
        status_text = "OK" if entry.result.ok else "ERROR"
        status_lbl = ttk.Label(header, text=status_text, font=("Rubik", 11, "bold"))
        status_lbl.configure(foreground=colors["ok"] if entry.result.ok else colors["error"])
        status_lbl.pack(side=tk.LEFT)
        ttk.Label(
            header,
            text=f"  {entry.label}  ·  {entry.result.latency_ms:.1f} ms  ·  {entry.timestamp} UTC",
            style="Muted.TLabel",
        ).pack(side=tk.LEFT)

        raw = entry.result.response_summary or entry.result.error or "(empty response)"
        body_to_display = raw
        # Strip leading "HTTP 200: " prefix for nicer formatting/highlighting when inspecting HTTP responses.
        if raw.startswith("HTTP ") and ": " in raw:
            prefix, payload = raw.split(": ", 1)
            fmt = detect_format(payload)
            try:
                formatted = pretty_print(payload, fmt)
            except ValueError:
                formatted = payload
            body_to_display = f"{prefix}\n\n{formatted}"
            highlight_fmt = fmt
        else:
            highlight_fmt = detect_format(raw)
            try:
                body_to_display = pretty_print(raw, highlight_fmt)
            except ValueError:
                body_to_display = raw.replace("\r", "\n")

        ttk.Button(
            header,
            text="Copy",
            command=lambda: self._copy(body_to_display),
        ).pack(side=tk.RIGHT)

        if entry.result.error and entry.result.response_summary:
            err_lbl = ttk.Label(self, text=f"Error: {entry.result.error}", font=("Rubik", 9, "bold"))
            err_lbl.configure(foreground=colors["error"])
            err_lbl.pack(anchor="w", padx=12, pady=(0, 4))

        frame = ttk.Frame(self)
        frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        border = get_border_color(theme)
        text = tk.Text(
            frame,
            wrap="none",
            font=("Menlo", 10),
            bd=0,
            padx=10,
            pady=10,
            highlightthickness=1,
            bg=theme.pane_bg,
            fg=theme.pane_fg,
            selectbackground=theme.select_bg,
            selectforeground=theme.select_fg,
            highlightbackground=border,
            highlightcolor=theme.accent,
        )
        v_scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=text.yview)
        h_scroll = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=text.xview)
        text.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)
        text.grid(row=0, column=0, sticky="nsew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        h_scroll.grid(row=1, column=0, sticky="ew")

        configure_tags(text, theme)
        text.insert("1.0", body_to_display)
        highlight(text, highlight_fmt)
        text.configure(state="disabled")

    def _copy(self, text: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)


class LogPanel(ttk.Frame):
    """Read-only, auto-scrolling log of send attempts with live stats and Response Inspector."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self._theme: Theme = get_theme(DEFAULT_THEME_NAME)
        self._entries_by_line: dict[int, LoggedEntry] = {}
        self._latencies: list[float] = []
        self._ok_count = 0
        self._err_count = 0

        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, padx=8, pady=(6, 4))
        ttk.Label(toolbar, text="ACTIVITY LOG", style="Section.TLabel").pack(side=tk.LEFT)
        self._stats_var = tk.StringVar(value="")
        ttk.Label(toolbar, textvariable=self._stats_var, style="Muted.TLabel").pack(side=tk.LEFT, padx=(12, 0))
        ttk.Button(toolbar, text="Clear", style="Subtle.TButton", command=self.clear).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(toolbar, text="Save Log…", style="Subtle.TButton", command=self.save_to_disk).pack(
            side=tk.RIGHT, padx=(4, 0)
        )

        body = ttk.Frame(self)
        body.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 6))
        self.text = tk.Text(
            body,
            height=8,
            state="disabled",
            wrap="word",
            font=("Menlo", 10),
            bd=0,
            padx=10,
            pady=8,
            highlightthickness=1,
            cursor="hand2",
        )
        self.text.tag_configure("ok", foreground="#15803D")
        self.text.tag_configure("error", foreground="#DC2626")
        self.text.tag_configure("info", foreground="#64748B")
        scrollbar = ttk.Scrollbar(body, command=self.text.yview)
        self.text.configure(yscrollcommand=scrollbar.set)
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.text.bind("<Double-Button-1>", self._inspect_clicked_line)
        self._last_was_info = False

    def apply_theme(self, theme: Theme) -> None:
        """Apply theme-aware colours for the log surface and semantic status tags."""
        self._theme = theme
        colors = get_semantic_colors(theme)
        border = get_border_color(theme)
        self.text.configure(
            bg=theme.pane_bg,
            fg=theme.pane_fg,
            insertbackground=theme.pane_fg,
            selectbackground=theme.select_bg,
            selectforeground=theme.select_fg,
            highlightbackground=border,
            highlightcolor=theme.accent,
        )
        self.text.tag_configure("ok", foreground=colors["ok"])
        self.text.tag_configure("error", foreground=colors["error"])
        self.text.tag_configure("info", foreground=colors["info"])

    def apply_preferences(self, prefs: AppPreferences) -> None:
        """Apply monospace font family and log font size preferences."""
        self.text.configure(font=(prefs.editor_font_family, prefs.log_font_size))

    def _update_stats(self) -> None:
        total = self._ok_count + self._err_count
        if total == 0:
            self._stats_var.set("")
            return
        avg_ms = sum(self._latencies) / total
        sorted_lat = sorted(self._latencies)
        p95_idx = min(len(sorted_lat) - 1, math.ceil(0.95 * len(sorted_lat)) - 1)
        p95_ms = sorted_lat[p95_idx]
        self._stats_var.set(
            f"{total} sent · {self._ok_count} OK · {self._err_count} ERR · "
            f"avg {avg_ms:.1f} ms · p95 {p95_ms:.1f} ms  (double-click row to inspect)"
        )

    def _inspect_clicked_line(self, event: tk.Event) -> None:
        index = self.text.index(f"@{event.x},{event.y}")
        line_num = int(index.split(".", 1)[0])
        entry = self._entries_by_line.get(line_num)
        if entry is not None:
            ResponseInspectorDialog(self, entry, self._theme)

    def append_info(self, text: str) -> None:
        """Log a plain informational line (e.g. announcing an in-progress send)."""
        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        line = f"[{timestamp}] {text}"

        self.text.configure(state="normal")
        if self.text.index("end-1c") != "1.0":
            self.text.insert(tk.END, "\n")  # blank line between entries for readability
        self.text.insert(tk.END, line + "\n", "info")
        self.text.see(tk.END)
        self.text.configure(state="disabled")
        self._last_was_info = True

    def append(self, message_name: str, result: SendResult) -> None:
        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        tag = "ok" if result.ok else "error"
        status = "OK" if result.ok else "ERROR"
        line = f"[{timestamp}] {message_name} — {status} ({result.latency_ms:.1f} ms)"
        detail = result.error or result.response_summary
        if detail:
            compact = " ".join(detail.splitlines())
            line += f" — {compact}"

        self.text.configure(state="normal")
        # Stays directly under its "Sending ..." info line rather than starting a new block.
        if not self._last_was_info and self.text.index("end-1c") != "1.0":
            self.text.insert(tk.END, "\n")
        line_num = int(self.text.index("end-1c").split(".", 1)[0])
        self.text.insert(tk.END, line + "\n", tag)
        self.text.see(tk.END)
        self.text.configure(state="disabled")
        self._last_was_info = False

        self._entries_by_line[line_num] = LoggedEntry(timestamp=timestamp, label=message_name, result=result)
        self._latencies.append(result.latency_ms)
        if result.ok:
            self._ok_count += 1
        else:
            self._err_count += 1
        self._update_stats()

    def clear(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", tk.END)
        self.text.configure(state="disabled")
        self._last_was_info = False
        self._entries_by_line.clear()
        self._latencies.clear()
        self._ok_count = 0
        self._err_count = 0
        self._update_stats()

    def save_to_disk(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save log", defaultextension=".log", filetypes=[("Log files", "*.log"), ("All files", "*.*")]
        )
        if not path:
            return
        content = self.text.get("1.0", "end-1c")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        except OSError as exc:
            messagebox.showerror("Ultra7", f"Could not save log: {exc}")
