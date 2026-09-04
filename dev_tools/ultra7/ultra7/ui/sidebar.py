"""Left sidebar listing persisted Ultra7 projects. Visibility is toggled by the app."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from ultra7.ui.themes import Theme, get_border_color


class Sidebar(ttk.Frame):
    """Lists project names; supports select, new, remove."""

    def __init__(
        self,
        parent: tk.Misc,
        on_select: Callable[[str], None],
        on_new: Callable[[], None],
        on_remove: Callable[[str], None],
    ) -> None:
        super().__init__(parent)
        self._on_select = on_select
        self._on_new = on_new
        self._on_remove = on_remove

        # Brand header — coloured top bar with app name.
        self._header = tk.Frame(self, height=44)
        self._header.pack(fill=tk.X)
        self._header.pack_propagate(False)
        self._header_label = tk.Label(
            self._header,
            text="☰  Ultra7",
            font=("Rubik", 13, "bold"),
            anchor="w",
            padx=10,
        )
        self._header_label.pack(fill=tk.BOTH, expand=True)

        # Subtle separator below the header.
        self._separator = tk.Frame(self, height=1)
        self._separator.pack(fill=tk.X)

        ttk.Label(self, text="Projects", font=("Rubik", 9)).pack(
            fill=tk.X, padx=10, pady=(8, 2), anchor="w"
        )

        listbox_frame = ttk.Frame(self)
        listbox_frame.pack(fill=tk.BOTH, expand=True, side=tk.TOP, padx=4)
        self.listbox = tk.Listbox(
            listbox_frame,
            exportselection=False,
            font=("Rubik", 10),
            activestyle="none",
            bd=0,
            highlightthickness=1,
            highlightbackground="#ccc",
        )
        listbox_scrollbar = ttk.Scrollbar(listbox_frame, orient=tk.VERTICAL, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=listbox_scrollbar.set)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        listbox_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.bind("<<ListboxSelect>>", self._handle_select)

        # Bottom button row with separator above.
        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=4, pady=(4, 0))
        button_row = ttk.Frame(self)
        button_row.pack(fill=tk.X, padx=4, pady=4)
        ttk.Button(button_row, text="New", command=self._on_new).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 2))
        ttk.Button(button_row, text="Remove", command=self._handle_remove).pack(
            side=tk.LEFT, expand=True, fill=tk.X, padx=(2, 0)
        )

    def apply_theme(self, theme: Theme) -> None:
        """Recolour the branded header and separators for the active theme."""
        self._header.configure(bg=theme.accent)
        self._header_label.configure(bg=theme.accent, fg=theme.select_fg)
        self._separator.configure(bg=get_border_color(theme))

    def _handle_select(self, _event: tk.Event) -> None:
        selection = self.listbox.curselection()
        if not selection:
            return
        name = self.listbox.get(selection[0])
        self._on_select(name)

    def _handle_remove(self) -> None:
        selection = self.listbox.curselection()
        if not selection:
            return
        name = self.listbox.get(selection[0])
        self._on_remove(name)

    def set_projects(self, names: list[str], select: str | None = None) -> None:
        self.listbox.delete(0, tk.END)
        for name in names:
            self.listbox.insert(tk.END, name)
        if select is not None and select in names:
            index = names.index(select)
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(index)
