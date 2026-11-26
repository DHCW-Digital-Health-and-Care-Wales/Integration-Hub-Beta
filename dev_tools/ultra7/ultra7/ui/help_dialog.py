"""Searchable, theme-aware built-in Help browser and About dialog for Ultra7."""
from __future__ import annotations

import platform
import re
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from ultra7.help_content import HelpTopic, build_help_topics, search_help_topics
from ultra7.ui.themes import (
    DEFAULT_THEME_NAME,
    Theme,
    blend_colors,
    get_accent_fg,
    get_border_color,
    get_muted_fg,
    get_theme,
    is_dark_theme,
)

_INLINE_TOKEN_RE = re.compile(r"(`[^`]+`|\*\*[^*]+\*\*)")


class HelpDialog(tk.Toplevel):
    """Non-modal searchable Help Guide window."""

    def __init__(
        self,
        parent: tk.Misc,
        initial_topic_id: str | None = None,
        theme: Theme | None = None,
    ) -> None:
        super().__init__(parent)
        self.title("Ultra7 — Help Guide")
        self.geometry("960x640")
        self._theme = theme or get_theme(DEFAULT_THEME_NAME)
        self.configure(bg=self._theme.bg)

        self._all_topics: tuple[HelpTopic, ...] = build_help_topics()
        self._visible_topics: list[HelpTopic] = list(self._all_topics)

        # Header bar
        header = ttk.Frame(self)
        header.pack(fill=tk.X, padx=14, pady=(12, 8))
        ttk.Label(header, text="Ultra7 Help Guide", font=("Rubik", 14, "bold")).pack(side=tk.LEFT)
        ttk.Button(header, text="Close", command=self.destroy).pack(side=tk.RIGHT)

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=14, pady=(0, 8))

        # Split layout: left topic list + search, right formatted reader
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 14))

        left = ttk.Frame(paned)
        paned.add(left, weight=0)

        search_row = ttk.Frame(left)
        search_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(search_row, text="Search", style="Muted.TLabel").pack(side=tk.LEFT, padx=(0, 6))
        self._search_var = tk.StringVar(value="")
        self._search_entry = ttk.Entry(search_row, textvariable=self._search_var, width=22)
        self._search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._search_entry.bind("<KeyRelease>", lambda _e: self._apply_search())
        ttk.Button(search_row, text="×", width=2, style="Subtle.TButton", command=self._clear_search).pack(
            side=tk.LEFT, padx=(4, 0)
        )

        border = get_border_color(self._theme)
        list_frame = ttk.Frame(left)
        list_frame.pack(fill=tk.BOTH, expand=True)
        self.topic_listbox = tk.Listbox(
            list_frame,
            width=30,
            exportselection=False,
            font=("Rubik", 10),
            activestyle="none",
            bd=0,
            highlightthickness=1,
            bg=self._theme.pane_bg,
            fg=self._theme.pane_fg,
            selectbackground=self._theme.select_bg,
            selectforeground=self._theme.select_fg,
            highlightbackground=border,
            highlightcolor=self._theme.accent,
        )
        list_scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.topic_listbox.yview)
        self.topic_listbox.configure(yscrollcommand=list_scroll.set)
        self.topic_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        list_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.topic_listbox.bind("<<ListboxSelect>>", self._on_topic_select)

        right = ttk.Frame(paned)
        paned.add(right, weight=1)
        right_inner = ttk.Frame(right)
        right_inner.pack(fill=tk.BOTH, expand=True, padx=(10, 0))
        right_inner.rowconfigure(0, weight=1)
        right_inner.columnconfigure(0, weight=1)

        self.reader = tk.Text(
            right_inner,
            wrap="word",
            font=("Rubik", 10),
            bd=0,
            padx=18,
            pady=14,
            spacing1=2,
            spacing3=4,
            highlightthickness=1,
            bg=self._theme.pane_bg,
            fg=self._theme.pane_fg,
            selectbackground=self._theme.select_bg,
            selectforeground=self._theme.select_fg,
            highlightbackground=border,
            highlightcolor=self._theme.accent,
        )
        reader_scroll = ttk.Scrollbar(right_inner, orient=tk.VERTICAL, command=self.reader.yview)
        self.reader.configure(yscrollcommand=reader_scroll.set)
        self.reader.grid(row=0, column=0, sticky="nsew")
        reader_scroll.grid(row=0, column=1, sticky="ns")

        self._configure_reader_tags()
        self._populate_topics(select_id=initial_topic_id)
        self.bind("<Escape>", lambda _e: self.destroy())

    def _configure_reader_tags(self) -> None:
        code_bg = blend_colors(self._theme.pane_bg, self._theme.accent, 0.16 if is_dark_theme(self._theme) else 0.10)
        muted = get_muted_fg(self._theme)
        self.reader.tag_configure("h1", font=("Rubik", 16, "bold"), foreground=self._theme.accent, spacing3=8)
        self.reader.tag_configure("h2", font=("Rubik", 12, "bold"), foreground=self._theme.fg, spacing1=12, spacing3=4)
        self.reader.tag_configure("category", font=("Rubik", 8, "bold"), foreground=muted, spacing3=2)
        self.reader.tag_configure("summary", font=("Rubik", 10, "italic"), foreground=muted, spacing3=10)
        self.reader.tag_configure("bold", font=("Rubik", 10, "bold"))
        self.reader.tag_configure("code", font=("Menlo", 10), background=code_bg, foreground=self._theme.syntax_keyword)
        self.reader.tag_configure("bullet", lmargin1=14, lmargin2=28)

    def _clear_search(self) -> None:
        self._search_var.set("")
        self._apply_search()

    def _apply_search(self) -> None:
        query = self._search_var.get()
        self._visible_topics = search_help_topics(query, self._all_topics)
        self._populate_topics()

    def _populate_topics(self, select_id: str | None = None) -> None:
        self.topic_listbox.delete(0, tk.END)
        select_idx = 0
        for idx, topic in enumerate(self._visible_topics):
            self.topic_listbox.insert(tk.END, f"  {topic.title}")
            if select_id is not None and topic.id == select_id:
                select_idx = idx
        if self._visible_topics:
            self.topic_listbox.selection_set(select_idx)
            self.topic_listbox.see(select_idx)
            self._render_topic(self._visible_topics[select_idx])
        else:
            self._render_empty_search()

    def select_topic(self, topic_id: str) -> None:
        """Select and display a specific topic by ID."""
        self._search_var.set("")
        self._visible_topics = list(self._all_topics)
        self._populate_topics(select_id=topic_id)

    def _on_topic_select(self, _event: tk.Event) -> None:
        sel = self.topic_listbox.curselection()
        if not sel:
            return
        self._render_topic(self._visible_topics[sel[0]])

    def _render_empty_search(self) -> None:
        self.reader.configure(state="normal")
        self.reader.delete("1.0", tk.END)
        self.reader.insert(tk.END, "No matching help topics found.\n", ("summary",))
        self.reader.configure(state="disabled")

    def _render_topic(self, topic: HelpTopic) -> None:
        self.reader.configure(state="normal")
        self.reader.delete("1.0", tk.END)
        self.reader.insert(tk.END, f"{topic.category.upper()}\n", ("category",))
        self.reader.insert(tk.END, f"{topic.summary}\n", ("summary",))

        for line in topic.body.splitlines():
            if line.startswith("# "):
                self.reader.insert(tk.END, line[2:] + "\n", ("h1",))
            elif line.startswith("## "):
                self.reader.insert(tk.END, line[3:] + "\n", ("h2",))
            elif line.startswith("- "):
                self._insert_inline("•  " + line[2:] + "\n", base_tags=("bullet",))
            elif re.match(r"^\d+\.\s", line):
                self._insert_inline(line + "\n", base_tags=("bullet",))
            else:
                self._insert_inline(line + "\n", base_tags=())

        self.reader.see("1.0")
        self.reader.configure(state="disabled")

    def _insert_inline(self, text: str, base_tags: tuple[str, ...]) -> None:
        pos = 0
        for match in _INLINE_TOKEN_RE.finditer(text):
            if match.start() > pos:
                self.reader.insert(tk.END, text[pos : match.start()], base_tags)
            token = match.group(0)
            if token.startswith("`") and token.endswith("`"):
                self.reader.insert(tk.END, f" {token[1:-1]} ", base_tags + ("code",))
            elif token.startswith("**") and token.endswith("**"):
                self.reader.insert(tk.END, token[2:-2], base_tags + ("bold",))
            pos = match.end()
        if pos < len(text):
            self.reader.insert(tk.END, text[pos:], base_tags)


class AboutDialog(tk.Toplevel):
    """Compact themed About dialog showing app metadata and local storage paths."""

    def __init__(self, parent: tk.Misc, theme: Theme | None = None) -> None:
        super().__init__(parent)
        self.title("About Ultra7")
        self.resizable(False, False)
        self.transient(parent)  # type: ignore[call-overload]
        active_theme = theme or get_theme(DEFAULT_THEME_NAME)
        self.configure(bg=active_theme.bg)

        banner = tk.Frame(self, bg=active_theme.accent, padx=20, pady=14)
        banner.pack(fill=tk.X)
        accent_fg = get_accent_fg(active_theme)
        tk.Label(
            banner,
            text="Ultra7",
            font=("Rubik", 18, "bold"),
            bg=active_theme.accent,
            fg=accent_fg,
            anchor="w",
        ).pack(fill=tk.X)
        tk.Label(
            banner,
            text="NHS Wales Integration Hub · MLLP / REST / SOAP Tester",
            font=("Rubik", 9),
            bg=active_theme.accent,
            fg=accent_fg,
            anchor="w",
        ).pack(fill=tk.X)

        body = ttk.Frame(self, padding=16)
        body.pack(fill=tk.BOTH, expand=True)
        info_lines = [
            ("Version", "0.1.0"),
            ("Organisation", "Digital Health and Care Wales (DHCW)"),
            ("Runtime", f"Python {platform.python_version()} · Tk {tk.TkVersion}"),
            ("Data folder", str(Path.home() / ".ultra7")),
        ]
        for row_idx, (label, val) in enumerate(info_lines):
            ttk.Label(body, text=label, style="Muted.TLabel").grid(
                row=row_idx, column=0, sticky="w", padx=(0, 14), pady=3
            )
            ttk.Label(body, text=val).grid(row=row_idx, column=1, sticky="w", pady=3)

        ttk.Button(body, text="Close", style="Accent.TButton", command=self.destroy).grid(
            row=len(info_lines), column=0, columnspan=2, pady=(14, 0)
        )
        self.bind("<Escape>", lambda _e: self.destroy())
        self.grab_set()
