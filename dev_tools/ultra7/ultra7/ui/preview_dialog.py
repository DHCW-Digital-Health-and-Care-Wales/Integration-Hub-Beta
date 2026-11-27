"""Dialog previewing the next N generated payloads for a message with iteration fields."""
from __future__ import annotations

import random
import tkinter as tk
from tkinter import ttk

from ultra7.formats.highlighting import configure_tags, highlight
from ultra7.iteration import apply_iteration
from ultra7.models import Message
from ultra7.ui.themes import DEFAULT_THEME_NAME, Theme, get_border_color, get_semantic_colors, get_theme


class IterationPreviewDialog(tk.Toplevel):
    """Shows the next N computed payloads before sending, highlighting each iterated value."""

    def __init__(
        self,
        parent: tk.Misc,
        message: Message,
        count: int = 5,
        theme: Theme | None = None,
    ) -> None:
        super().__init__(parent)
        self.title(f"Preview Sends — {message.name}")
        self.geometry("840x560")
        self.transient(parent)  # type: ignore[call-overload]
        self._message = message
        self._theme = theme or get_theme(DEFAULT_THEME_NAME)
        self.configure(bg=self._theme.bg)

        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=12, pady=(10, 4))
        ttk.Label(top, text="Preview count", style="Muted.TLabel").pack(side=tk.LEFT)
        self._count_var = tk.StringVar(value=str(max(1, count)))
        ttk.Entry(top, textvariable=self._count_var, width=6).pack(side=tk.LEFT, padx=(6, 8))
        ttk.Button(top, text="Refresh", command=self._render).pack(side=tk.LEFT)
        ttk.Button(top, text="Close", command=self.destroy).pack(side=tk.RIGHT)

        ttk.Label(
            self,
            text="Highlighted values change on each repeat when using ▶ Send with Repeat > 1.",
            style="Muted.TLabel",
        ).pack(anchor="w", padx=12, pady=(0, 6))

        body = ttk.Frame(self)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)

        border = get_border_color(self._theme)
        self.text = tk.Text(
            body,
            wrap="none",
            font=("Menlo", 10),
            bd=0,
            padx=10,
            pady=10,
            highlightthickness=1,
            bg=self._theme.pane_bg,
            fg=self._theme.pane_fg,
            selectbackground=self._theme.select_bg,
            selectforeground=self._theme.select_fg,
            highlightbackground=border,
            highlightcolor=self._theme.accent,
        )
        v_scroll = ttk.Scrollbar(body, orient=tk.VERTICAL, command=self.text.yview)
        h_scroll = ttk.Scrollbar(body, orient=tk.HORIZONTAL, command=self.text.xview)
        self.text.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        h_scroll.grid(row=1, column=0, sticky="ew")

        configure_tags(self.text, self._theme)
        colors = get_semantic_colors(self._theme)
        self.text.tag_configure("header", foreground=self._theme.accent, font=("Rubik", 10, "bold"))
        self.text.tag_configure("iter-val", background=colors["iterate_bg"], foreground=colors["iterate_fg"])
        self._render()
        self.bind("<Escape>", lambda _e: self.destroy())

    def _render(self) -> None:
        try:
            total = max(1, min(50, int(self._count_var.get())))
        except ValueError:
            total = 5
        specs = sorted(self._message.all_iterations(), key=lambda s: s.start)
        rng = random.Random(42)  # nosec B311 - deterministic preview

        self.text.configure(state="normal")
        self.text.delete("1.0", tk.END)
        highlight_spans: list[tuple[str, str]] = []

        for idx in range(total):
            header = f"─── Send #{idx + 1} ────────────────────────────────────────\n"
            self.text.insert(tk.END, header, ("header",))
            base_idx = self.text.index("end-1c")
            # Build rendered text left-to-right so we know the exact replaced spans to highlight.
            content = self._message.content
            cursor = 0
            out_parts: list[str] = []
            local_spans: list[tuple[int, int]] = []
            out_len = 0
            for spec in specs:
                if not (0 <= spec.start < spec.end <= len(content)) or spec.start < cursor:
                    continue
                prefix = content[cursor : spec.start]
                out_parts.append(prefix)
                out_len += len(prefix)
                # Compute replacement for this single spec.
                replaced_full = apply_iteration(content, spec, idx, rng=rng)
                delta = len(replaced_full) - len(content)
                replacement = replaced_full[spec.start : spec.end + delta]
                local_spans.append((out_len, out_len + len(replacement)))
                out_parts.append(replacement)
                out_len += len(replacement)
                cursor = spec.end
            out_parts.append(content[cursor:])
            rendered = "".join(out_parts)
            self.text.insert(tk.END, rendered + "\n\n")
            for s, e in local_spans:
                highlight_spans.append((f"{base_idx}+{s}c", f"{base_idx}+{e}c"))

        highlight(self.text, self._message.format)
        for start_ref, end_ref in highlight_spans:
            self.text.tag_add("iter-val", start_ref, end_ref)
        self.text.tag_raise("iter-val")
        self.text.configure(state="disabled")
