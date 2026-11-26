"""Side-by-side diff viewer for comparing two messages or responses."""
from __future__ import annotations

import difflib
import tkinter as tk
from tkinter import ttk

from ultra7.models import Message
from ultra7.ui.themes import DEFAULT_THEME_NAME, Theme, get_border_color, get_theme, is_dark_theme


def compute_side_by_side_diff(
    left_text: str, right_text: str
) -> tuple[list[tuple[str, str]], list[tuple[str, str]], int, int]:
    """Return aligned ``(left_rows, right_rows, added_count, removed_count)``.

    Each row is ``(line_text, tag)`` where ``tag`` is one of
    ``""``, ``"added"``, ``"removed"``, ``"changed"``, or ``"empty"``.
    """
    left_lines = left_text.splitlines()
    right_lines = right_text.splitlines()
    matcher = difflib.SequenceMatcher(None, left_lines, right_lines)

    left_rows: list[tuple[str, str]] = []
    right_rows: list[tuple[str, str]] = []
    added = 0
    removed = 0

    for opcode, i1, i2, j1, j2 in matcher.get_opcodes():
        if opcode == "equal":
            for l_line, r_line in zip(left_lines[i1:i2], right_lines[j1:j2]):
                left_rows.append((l_line, ""))
                right_rows.append((r_line, ""))
        elif opcode == "replace":
            l_chunk = left_lines[i1:i2]
            r_chunk = right_lines[j1:j2]
            span = max(len(l_chunk), len(r_chunk))
            removed += len(l_chunk)
            added += len(r_chunk)
            for idx in range(span):
                left_rows.append((l_chunk[idx], "changed") if idx < len(l_chunk) else ("", "empty"))
                right_rows.append((r_chunk[idx], "changed") if idx < len(r_chunk) else ("", "empty"))
        elif opcode == "delete":
            removed += i2 - i1
            for l_line in left_lines[i1:i2]:
                left_rows.append((l_line, "removed"))
                right_rows.append(("", "empty"))
        elif opcode == "insert":
            added += j2 - j1
            for r_line in right_lines[j1:j2]:
                left_rows.append(("", "empty"))
                right_rows.append((r_line, "added"))

    return left_rows, right_rows, added, removed


class DiffDialog(tk.Toplevel):
    """Side-by-side message/response diff window."""

    def __init__(
        self,
        parent: tk.Misc,
        messages: list[Message],
        initial_left: int = 0,
        initial_right: int = 1,
        theme: Theme | None = None,
    ) -> None:
        super().__init__(parent)
        self.title("Compare Messages")
        self.geometry("1040x640")
        self.transient(parent)  # type: ignore[call-overload]
        self._theme = theme or get_theme(DEFAULT_THEME_NAME)
        self.configure(bg=self._theme.bg)

        self._messages = messages
        names = [f"{idx + 1}. {m.name}" for idx, m in enumerate(messages)]
        left_idx = max(0, min(initial_left, len(names) - 1)) if names else 0
        right_idx = max(0, min(initial_right, len(names) - 1)) if names else 0

        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=12, pady=(10, 6))
        ttk.Label(top, text="Left", style="Muted.TLabel").pack(side=tk.LEFT)
        self._left_var = tk.StringVar(value=names[left_idx] if names else "")
        ttk.OptionMenu(
            top, self._left_var, self._left_var.get(), *names, command=lambda _v: self._render()
        ).pack(side=tk.LEFT, padx=(6, 16))

        ttk.Label(top, text="Right", style="Muted.TLabel").pack(side=tk.LEFT)
        self._right_var = tk.StringVar(value=names[right_idx] if names else "")
        ttk.OptionMenu(
            top, self._right_var, self._right_var.get(), *names, command=lambda _v: self._render()
        ).pack(side=tk.LEFT, padx=(6, 16))

        self._summary_var = tk.StringVar(value="")
        ttk.Label(top, textvariable=self._summary_var, style="Muted.TLabel").pack(side=tk.RIGHT)

        body = ttk.Frame(self)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 10))
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        border = get_border_color(self._theme)
        self.left_text = tk.Text(
            body,
            wrap="none",
            font=("Menlo", 10),
            bd=0,
            padx=8,
            pady=8,
            highlightthickness=1,
            bg=self._theme.pane_bg,
            fg=self._theme.pane_fg,
            highlightbackground=border,
            highlightcolor=self._theme.accent,
        )
        self.right_text = tk.Text(
            body,
            wrap="none",
            font=("Menlo", 10),
            bd=0,
            padx=8,
            pady=8,
            highlightthickness=1,
            bg=self._theme.pane_bg,
            fg=self._theme.pane_fg,
            highlightbackground=border,
            highlightcolor=self._theme.accent,
        )

        self._v_scroll = ttk.Scrollbar(body, orient=tk.VERTICAL, command=self._on_vscroll)
        self.left_text.configure(yscrollcommand=self._sync_left_y)
        self.right_text.configure(yscrollcommand=self._sync_right_y)

        self.left_text.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        self.right_text.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        self._v_scroll.grid(row=0, column=2, sticky="ns")

        self._configure_diff_tags()
        self._render()

    def _configure_diff_tags(self) -> None:
        if is_dark_theme(self._theme):
            added_bg, removed_bg, changed_bg, empty_bg = "#14432A", "#4C1D24", "#4A3A15", "#2A2D34"
        else:
            added_bg, removed_bg, changed_bg, empty_bg = "#DCFCE7", "#FEE2E2", "#FEF3C7", "#F1F5F9"
        for widget in (self.left_text, self.right_text):
            widget.tag_configure("added", background=added_bg)
            widget.tag_configure("removed", background=removed_bg)
            widget.tag_configure("changed", background=changed_bg)
            widget.tag_configure("empty", background=empty_bg)

    def _on_vscroll(self, *args: object) -> None:
        self.left_text.yview(*args)  # type: ignore[arg-type]
        self.right_text.yview(*args)  # type: ignore[arg-type]

    def _sync_left_y(self, first: float, last: float) -> None:
        self._v_scroll.set(first, last)
        self.right_text.yview_moveto(float(first))

    def _sync_right_y(self, first: float, last: float) -> None:
        self._v_scroll.set(first, last)
        self.left_text.yview_moveto(float(first))

    def _index_for(self, label: str) -> int:
        try:
            return int(label.split(".", 1)[0]) - 1
        except (ValueError, IndexError):
            return 0

    def _render(self) -> None:
        if not self._messages:
            return
        l_msg = self._messages[self._index_for(self._left_var.get())]
        r_msg = self._messages[self._index_for(self._right_var.get())]
        left_rows, right_rows, added, removed = compute_side_by_side_diff(l_msg.content, r_msg.content)

        for widget, rows in ((self.left_text, left_rows), (self.right_text, right_rows)):
            widget.configure(state="normal")
            widget.delete("1.0", tk.END)
            for idx, (line, tag) in enumerate(rows, start=1):
                prefix = f"{idx:3d}  " if tag != "empty" else "     "
                widget.insert(tk.END, prefix + line + "\n", (tag,) if tag else ())
            widget.configure(state="disabled")

        if added == 0 and removed == 0:
            self._summary_var.set("Identical")
        else:
            self._summary_var.set(f"+{added} / -{removed} line(s)")
