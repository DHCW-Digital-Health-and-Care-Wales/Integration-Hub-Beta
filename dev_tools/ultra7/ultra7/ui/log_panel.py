"""Togglable bottom panel showing a log of sends and responses."""
from __future__ import annotations

import tkinter as tk
from datetime import datetime, timezone
from tkinter import filedialog, messagebox, ttk

from ultra7.senders.base import SendResult


class LogPanel(ttk.Frame):
    """Read-only, auto-scrolling log of send attempts. Visibility toggled by the app."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)

        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, padx=8, pady=(4, 2))
        ttk.Label(toolbar, text="Log", font=("Rubik", 9)).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="Clear", command=self.clear).pack(side=tk.RIGHT, padx=2)
        ttk.Button(toolbar, text="Save to disk…", command=self.save_to_disk).pack(side=tk.RIGHT, padx=2)

        self.text = tk.Text(
            self,
            height=8,
            state="disabled",
            wrap="word",
            font=("Menlo", 10),
            bd=0,
            padx=8,
            pady=8,
            highlightthickness=1,
        )
        self.text.tag_configure("ok", foreground="#1A7A3F")
        self.text.tag_configure("error", foreground="#C0392B")
        self.text.tag_configure("info", foreground="#6B7280")
        scrollbar = ttk.Scrollbar(self, command=self.text.yview)
        self.text.configure(yscrollcommand=scrollbar.set)
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._last_was_info = False

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
            line += f" — {detail}"

        self.text.configure(state="normal")
        # Stays directly under its "Sending ..." info line rather than starting a new block.
        if not self._last_was_info and self.text.index("end-1c") != "1.0":
            self.text.insert(tk.END, "\n")
        self.text.insert(tk.END, line + "\n", tag)
        self.text.see(tk.END)
        self.text.configure(state="disabled")
        self._last_was_info = False

    def clear(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", tk.END)
        self.text.configure(state="disabled")
        self._last_was_info = False

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
