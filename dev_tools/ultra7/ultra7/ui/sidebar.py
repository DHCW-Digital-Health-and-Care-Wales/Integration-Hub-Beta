"""Left sidebar listing persisted Ultra7 projects. Visibility is toggled by the app."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from ultra7.ui.themes import Theme, get_border_color

# DHCW brand accent colour for highlighting
HIGHLIGHT_BG = "#E8F4FC"  # Light blue highlight
HIGHLIGHT_FG = "#1B294A"  # Dark text on highlight


class ProjectItem(tk.Frame):
    """A single project row with checkbox and label."""

    def __init__(
        self,
        parent: tk.Misc,
        name: str,
        on_checkbox_toggle: Callable[[str], None],
        on_name_click: Callable[[str], None],
    ) -> None:
        super().__init__(parent, highlightthickness=0)
        self.name = name
        self._on_checkbox_toggle = on_checkbox_toggle
        self._on_name_click = on_name_click
        self._is_selected = False
        self._parent_bg = "white"
        self._parent_fg = "black"

        self._var = tk.IntVar(value=0)

        self.checkbox = tk.Checkbutton(
            self,
            variable=self._var,
            relief="flat",
            borderwidth=0,
            selectcolor="",
            command=self._handle_checkbox_toggle,
        )
        self.checkbox.pack(side=tk.LEFT)

        self.label = tk.Label(
            self,
            text=name,
            font=("Rubik", 10),
            cursor="hand2",
            anchor="w",
            padx=4,
        )
        self.label.pack(side=tk.LEFT, expand=True, fill=tk.X)
        self.label.bind("<Button-1>", self._handle_name_click)

    def _handle_checkbox_toggle(self) -> None:
        self._on_checkbox_toggle(self.name)

    def _handle_name_click(self, _event: tk.Event) -> None:
        self._on_name_click(self.name)

    def set_checked(self, checked: bool) -> None:
        self._var.set(1 if checked else 0)

    def is_checked(self) -> bool:
        return self._var.get() == 1

    def set_selected(self, selected: bool) -> None:
        """Set whether this project row is currently selected (highlighted)."""
        self._is_selected = selected
        if selected:
            self.configure(bg=HIGHLIGHT_BG)
            self.label.configure(bg=HIGHLIGHT_BG, fg=HIGHLIGHT_FG)
        else:
            self.configure(bg=self._parent_bg)
            self.label.configure(bg=self._parent_bg, fg=self._parent_fg)


class Sidebar(ttk.Frame):
    """Lists project names with checkboxes; supports select, new, remove, and batch run."""

    def __init__(
        self,
        parent: tk.Misc,
        on_select: Callable[[str], None],
        on_new: Callable[[], None],
        on_remove: Callable[[str], None],
        on_run_selected: Callable[[list[str]], None],
    ) -> None:
        super().__init__(parent)
        self._on_select = on_select
        self._on_new = on_new
        self._on_remove = on_remove
        self._on_run_selected = on_run_selected
        self._project_items: list[ProjectItem] = []
        self._selected_name: str | None = None

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

        # Scrollable frame for project list.
        listbox_frame = ttk.Frame(self)
        listbox_frame.pack(fill=tk.BOTH, expand=True, side=tk.TOP, padx=4)
        self._list_canvas = tk.Canvas(listbox_frame, height=200, bg="#f5f5f5", highlightthickness=0)
        scrollbar = ttk.Scrollbar(listbox_frame, orient=tk.VERTICAL, command=self._list_canvas.yview)
        self._list_inner_frame = tk.Frame(self._list_canvas)
        self._list_canvas.create_window((0, 0), window=self._list_inner_frame, anchor="nw", tags="inner")
        self._list_canvas.configure(yscrollcommand=scrollbar.set)
        self._list_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._list_inner_frame.bind("<Configure>", self._configure_scrollregion)

        # Bottom button row with separator above.
        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=4, pady=(4, 0))
        button_row = ttk.Frame(self)
        button_row.pack(fill=tk.X, padx=4, pady=4)
        # Use grid with weights inversely proportional to text length
        # "New"=3, "Remove"=6, "Run"=3 → weights: 2, 1, 2
        self._new_btn = ttk.Button(button_row, text="New", command=self._on_new)
        self._remove_btn = ttk.Button(button_row, text="Remove", command=self._handle_remove)
        self._run_btn = ttk.Button(button_row, text="Run", command=self._handle_run)
        self._new_btn.grid(row=0, column=0, sticky="ew", padx=1)
        self._remove_btn.grid(row=0, column=1, sticky="ew", padx=1)
        self._run_btn.grid(row=0, column=2, sticky="ew", padx=1)
        button_row.columnconfigure(0, weight=2)
        button_row.columnconfigure(1, weight=1)
        button_row.columnconfigure(2, weight=2)

    def _configure_scrollregion(self, event: tk.Event) -> None:
        self._list_canvas.configure(scrollregion=self._list_canvas.bbox("all"))

    def apply_theme(self, theme: Theme) -> None:
        """Recolour the branded header and separators for the active theme."""
        self._header.configure(bg=theme.accent)
        self._header_label.configure(bg=theme.accent, fg=theme.select_fg)
        self._separator.configure(bg=get_border_color(theme))
        # Update parent background colors for all items
        for item in self._project_items:
            item._parent_bg = theme.bg
            item._parent_fg = theme.fg
            # Only reset non-selected items; selected items keep their highlight
            if item.name != self._selected_name:
                item.set_selected(False)

    def _handle_select(self, name: str) -> None:
        # Update selection - clear old highlight, set new one
        old_selected = self._selected_name
        self._selected_name = name

        # Reset previously selected item
        if old_selected and old_selected != name:
            for item in self._project_items:
                if item.name == old_selected:
                    item.set_selected(False)
                    break

        # Highlight newly selected item
        for item in self._project_items:
            if item.name == name:
                item.set_selected(True)
                break

        self._on_select(name)

    def _handle_remove(self) -> None:
        if self._selected_name is not None:
            self._on_remove(self._selected_name)

    def _handle_run(self) -> None:
        selected = self.get_selected_projects()
        if selected:
            self._on_run_selected(selected)
        else:
            self._on_run_selected([])

    def set_projects(self, names: list[str], select: str | None = None) -> None:
        # Clear existing items
        for item in self._project_items:
            item.destroy()
        self._project_items = []
        self._selected_name = None

        # Create new items
        for name in names:
            item = ProjectItem(
                self._list_inner_frame,
                name,
                self._on_checkbox_toggle,
                self._handle_select,
            )
            item.pack(fill=tk.X, padx=2, pady=1)
            self._project_items.append(item)

        # Set initial selection
        if select is not None and select in names:
            self._selected_name = select
            for item in self._project_items:
                if item.name == select:
                    item.set_selected(True)
                    break

        # Store default parent background/foreground for new items
        # This will be updated when apply_theme is called
        for item in self._project_items:
            item._parent_bg = "white"
            item._parent_fg = "black"

    def _on_checkbox_toggle(self, name: str) -> None:
        # Find if this project is currently selected and reselect it
        item = next((p for p in self._project_items if p.name == name), None)
        if item:
            self._handle_select(name)

    def get_selected_projects(self) -> list[str]:
        """Return list of project names that have their checkbox checked."""
        return [item.name for item in self._project_items if item.is_checked()]

    def check_project(self, name: str) -> None:
        """Check the checkbox for a project by name."""
        for item in self._project_items:
            if item.name == name:
                item.set_checked(True)
                break

    def uncheck_project(self, name: str) -> None:
        """Uncheck the checkbox for a project by name."""
        for item in self._project_items:
            if item.name == name:
                item.set_checked(False)
                break

    def check_all(self) -> None:
        """Check all project checkboxes."""
        for item in self._project_items:
            item.set_checked(True)

    def uncheck_all(self) -> None:
        """Uncheck all project checkboxes."""
        for item in self._project_items:
            item.set_checked(False)
