"""Left sidebar listing persisted Ultra7 projects. Visibility is toggled by the app."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from ultra7.settings import AppPreferences
from ultra7.ui.themes import DEFAULT_THEME_NAME, Theme, get_accent_fg, get_border_color, get_hover_bg, get_theme


class ProjectItem(tk.Frame):
    """A single project row with checkbox and label."""

    def __init__(
        self,
        parent: tk.Misc,
        name: str,
        on_checkbox_toggle: Callable[[str], None],
        on_name_click: Callable[[str], None],
        theme: Theme,
    ) -> None:
        super().__init__(parent, highlightthickness=0, pady=3, padx=4)
        self.name = name
        self._on_checkbox_toggle = on_checkbox_toggle
        self._on_name_click = on_name_click
        self._is_selected = False
        self._is_hovered = False
        self._theme = theme

        self._var = tk.IntVar(value=0)

        self.checkbox = tk.Checkbutton(
            self,
            variable=self._var,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            cursor="hand2",
            command=self._handle_checkbox_toggle,
        )
        self.checkbox.pack(side=tk.LEFT, padx=(2, 0))

        self.label = tk.Label(
            self,
            text=name,
            font=("Rubik", 10),
            cursor="hand2",
            anchor="w",
            padx=6,
            pady=2,
        )
        self.label.pack(side=tk.LEFT, expand=True, fill=tk.X)
        self.label.bind("<Button-1>", self._handle_name_click)
        for widget in (self, self.label, self.checkbox):
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)
        self._apply_colors()

    def _on_enter(self, _event: tk.Event) -> None:
        self._is_hovered = True
        self._apply_colors()

    def _on_leave(self, _event: tk.Event) -> None:
        self._is_hovered = False
        self._apply_colors()

    def _handle_checkbox_toggle(self) -> None:
        self._on_checkbox_toggle(self.name)

    def _handle_name_click(self, _event: tk.Event) -> None:
        self._on_name_click(self.name)

    def set_checked(self, checked: bool) -> None:
        self._var.set(1 if checked else 0)

    def is_checked(self) -> bool:
        return self._var.get() == 1

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._apply_colors()

    def apply_font(self, family: str, size: int) -> None:
        self.label.configure(font=(family, size))

    def set_selected(self, selected: bool) -> None:
        """Set whether this project row is currently selected (highlighted)."""
        self._is_selected = selected
        self._apply_colors()

    def _apply_colors(self) -> None:
        if self._is_selected:
            bg = self._theme.select_bg
            fg = self._theme.select_fg
        elif self._is_hovered:
            bg = get_hover_bg(self._theme)
            fg = self._theme.pane_fg
        else:
            bg = self._theme.pane_bg
            fg = self._theme.pane_fg
        self.configure(bg=bg)
        self.label.configure(bg=bg, fg=fg)
        self.checkbox.configure(bg=bg, activebackground=bg, fg=fg, selectcolor=bg)


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
        self._theme: Theme = get_theme(DEFAULT_THEME_NAME)
        self._ui_font: tuple[str, int] = ("Rubik", 10)

        # Brand header — coloured top bar with app name.
        self._header = tk.Frame(self, height=48)
        self._header.pack(fill=tk.X)
        self._header.pack_propagate(False)
        self._header_label = tk.Label(
            self._header,
            text="Ultra7",
            font=("Rubik", 14, "bold"),
            anchor="w",
            padx=14,
        )
        self._header_label.pack(side=tk.LEFT, fill=tk.Y)
        self._header_badge = tk.Label(
            self._header,
            text="HL7 · REST · SOAP",
            font=("Rubik", 8),
            anchor="e",
            padx=12,
        )
        self._header_badge.pack(side=tk.RIGHT, fill=tk.Y)

        # Subtle separator below the header.
        self._separator = tk.Frame(self, height=1)
        self._separator.pack(fill=tk.X)

        ttk.Label(self, text="PROJECTS", style="Section.TLabel").pack(
            fill=tk.X, padx=12, pady=(10, 4), anchor="w"
        )

        # Scrollable frame for project list.
        listbox_frame = ttk.Frame(self)
        listbox_frame.pack(fill=tk.BOTH, expand=True, side=tk.TOP, padx=8, pady=(0, 4))
        self._list_canvas = tk.Canvas(listbox_frame, height=200, bg="#f5f5f5", highlightthickness=1)
        scrollbar = ttk.Scrollbar(listbox_frame, orient=tk.VERTICAL, command=self._list_canvas.yview)
        self._list_inner_frame = tk.Frame(self._list_canvas)
        self._inner_window_id = self._list_canvas.create_window(
            (0, 0), window=self._list_inner_frame, anchor="nw", tags="inner"
        )
        self._list_canvas.configure(yscrollcommand=scrollbar.set)
        self._list_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._list_inner_frame.bind("<Configure>", self._configure_scrollregion)
        self._list_canvas.bind("<Configure>", self._resize_inner_frame)

        # Bottom button row with separator above.
        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=8, pady=(4, 0))
        button_row = ttk.Frame(self)
        button_row.pack(fill=tk.X, padx=8, pady=8)
        self._new_btn = ttk.Button(button_row, text="+ New", command=self._on_new)
        self._remove_btn = ttk.Button(button_row, text="Remove", style="Danger.TButton", command=self._handle_remove)
        self._run_btn = ttk.Button(button_row, text="▶ Run", style="Accent.TButton", command=self._handle_run)
        self._new_btn.grid(row=0, column=0, sticky="ew", padx=(0, 3))
        self._remove_btn.grid(row=0, column=1, sticky="ew", padx=3)
        self._run_btn.grid(row=0, column=2, sticky="ew", padx=(3, 0))
        button_row.columnconfigure(0, weight=1)
        button_row.columnconfigure(1, weight=1)
        button_row.columnconfigure(2, weight=1)

    def _configure_scrollregion(self, _event: tk.Event) -> None:
        self._list_canvas.configure(scrollregion=self._list_canvas.bbox("all"))

    def _resize_inner_frame(self, event: tk.Event) -> None:
        self._list_canvas.itemconfigure(self._inner_window_id, width=event.width)

    def apply_theme(self, theme: Theme) -> None:
        """Recolour the branded header and separators for the active theme."""
        self._theme = theme
        border = get_border_color(theme)
        accent_fg = get_accent_fg(theme)
        self._header.configure(bg=theme.accent)
        self._header_label.configure(bg=theme.accent, fg=accent_fg)
        self._header_badge.configure(bg=theme.accent, fg=accent_fg)
        self._separator.configure(bg=border)
        self._list_canvas.configure(bg=theme.pane_bg, highlightbackground=border, highlightcolor=theme.accent)
        self._list_inner_frame.configure(bg=theme.pane_bg)
        for item in self._project_items:
            item.apply_theme(theme)

    def apply_preferences(self, prefs: AppPreferences) -> None:
        """Apply UI font family and size to sidebar header and project rows."""
        self._ui_font = (prefs.ui_font_family, prefs.ui_font_size)
        self._header_label.configure(font=(prefs.ui_font_family, prefs.ui_font_size + 4, "bold"))
        self._header_badge.configure(font=(prefs.ui_font_family, max(7, prefs.ui_font_size - 2)))
        for item in self._project_items:
            item.apply_font(*self._ui_font)

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

        # Create new items using the active theme and font
        for name in names:
            item = ProjectItem(
                self._list_inner_frame,
                name,
                self._on_checkbox_toggle,
                self._handle_select,
                self._theme,
            )
            item.apply_font(*self._ui_font)
            item.pack(fill=tk.X, padx=2, pady=1)
            self._project_items.append(item)

        # Set initial selection
        if select is not None and select in names:
            self._selected_name = select
            for item in self._project_items:
                if item.name == select:
                    item.set_selected(True)
                    break

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
