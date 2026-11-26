"""Modal Preferences dialog for themes, fonts, sizes, and editor behaviour."""
from __future__ import annotations

import tkinter as tk
from dataclasses import replace
from tkinter import font as tkfont
from tkinter import ttk
from typing import Callable

from ultra7.formats.highlighting import configure_tags, highlight
from ultra7.settings import (
    MAX_EDITOR_FONT_SIZE,
    MAX_LOG_FONT_SIZE,
    MAX_TREE_ROW_HEIGHT,
    MAX_UI_FONT_SIZE,
    MIN_EDITOR_FONT_SIZE,
    MIN_LOG_FONT_SIZE,
    MIN_TREE_ROW_HEIGHT,
    MIN_UI_FONT_SIZE,
    AppPreferences,
)
from ultra7.ui.themes import THEMES, get_border_color, get_theme

_PREFERRED_UI_FONTS = (
    "Rubik",
    "SF Pro Text",
    "Helvetica Neue",
    "Inter",
    "Segoe UI",
    "Arial",
    "DejaVu Sans",
    "TkDefaultFont",
)

_PREFERRED_MONO_FONTS = (
    "Menlo",
    "SF Mono",
    "JetBrains Mono",
    "Fira Code",
    "Monaco",
    "Cascadia Code",
    "Consolas",
    "Courier New",
    "DejaVu Sans Mono",
    "TkFixedFont",
)

_SAMPLE_HL7 = (
    "MSH|^~\\&|PHW|SITE|MPI|DHCW|202501011200||ADT^A01|000001|P|2.5\n"
    "PID|1||9991234568^^^NHS^NH||DOE^JANE||19850615|F"
)


def _available_font_choices(preferred: tuple[str, ...], current: str) -> list[str]:
    try:
        installed = set(tkfont.families())
    except tk.TclError:
        installed = set()
    choices: list[str] = []
    for name in (current, *preferred):
        if name and name not in choices and (not installed or name in installed or name.startswith("Tk")):
            choices.append(name)
    if not choices:
        choices.append(current or "TkDefaultFont")
    return choices


class PreferencesDialog(tk.Toplevel):
    """Configures appearance (theme, swatches), fonts, sizes, and editor options."""

    def __init__(
        self,
        parent: tk.Misc,
        preferences: AppPreferences,
        on_apply: Callable[[AppPreferences], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.title("Ultra7 — Preferences")
        self.resizable(False, False)
        self.transient(parent)  # type: ignore[call-overload]
        self._on_apply = on_apply
        self.result: AppPreferences | None = None

        active_theme = get_theme(preferences.theme)
        self.configure(bg=active_theme.bg)

        self._theme_var = tk.StringVar(value=active_theme.name)
        self._ui_font_var = tk.StringVar(value=preferences.ui_font_family)
        self._ui_size_var = tk.StringVar(value=str(preferences.ui_font_size))
        self._ed_font_var = tk.StringVar(value=preferences.editor_font_family)
        self._ed_size_var = tk.StringVar(value=str(preferences.editor_font_size))
        self._log_size_var = tk.StringVar(value=str(preferences.log_font_size))
        self._row_height_var = tk.StringVar(value=str(preferences.tree_row_height))
        self._wrap_var = tk.BooleanVar(value=preferences.editor_word_wrap)
        self._left_view_var = tk.StringVar(value=preferences.default_left_view)
        self._auto_expand_var = tk.BooleanVar(value=preferences.auto_expand_structure)

        body = ttk.Frame(self, padding=16)
        body.pack(fill=tk.BOTH, expand=True)

        ttk.Label(body, text="Preferences", font=("Rubik", 14, "bold")).grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 10)
        )

        # -- Appearance section -----------------------------------------------
        row = 1
        ttk.Label(body, text="APPEARANCE", style="Section.TLabel").grid(
            row=row, column=0, columnspan=4, sticky="w", pady=(4, 4)
        )
        row += 1

        ttk.Label(body, text="Colour Theme").grid(row=row, column=0, sticky="w", padx=(0, 10), pady=4)
        theme_names = [t.name for t in THEMES]
        ttk.OptionMenu(
            body,
            self._theme_var,
            self._theme_var.get(),
            *theme_names,
            command=lambda _v: self._refresh_preview(),
        ).grid(row=row, column=1, columnspan=2, sticky="ew", pady=4)

        self._swatch_frame = ttk.Frame(body)
        self._swatch_frame.grid(row=row, column=3, sticky="w", padx=(10, 0), pady=4)
        self._swatches: list[tk.Frame] = []
        for _ in range(6):
            swatch = tk.Frame(self._swatch_frame, width=18, height=18, bd=1, relief="solid")
            swatch.pack_propagate(False)
            swatch.pack(side=tk.LEFT, padx=2)
            self._swatches.append(swatch)
        row += 1

        # -- Typography section -----------------------------------------------
        ttk.Separator(body, orient=tk.HORIZONTAL).grid(row=row, column=0, columnspan=4, sticky="ew", pady=(10, 6))
        row += 1
        ttk.Label(body, text="TYPOGRAPHY", style="Section.TLabel").grid(
            row=row, column=0, columnspan=4, sticky="w", pady=(0, 4)
        )
        row += 1

        ui_fonts = _available_font_choices(_PREFERRED_UI_FONTS, preferences.ui_font_family)
        ttk.Label(body, text="UI Font").grid(row=row, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.OptionMenu(
            body,
            self._ui_font_var,
            self._ui_font_var.get(),
            *ui_fonts,
            command=lambda _v: self._refresh_preview(),
        ).grid(row=row, column=1, sticky="ew", pady=4)
        ttk.Label(body, text="Size").grid(row=row, column=2, sticky="e", padx=(12, 6), pady=4)
        ttk.Spinbox(
            body,
            from_=MIN_UI_FONT_SIZE,
            to=MAX_UI_FONT_SIZE,
            textvariable=self._ui_size_var,
            width=5,
            command=self._refresh_preview,
        ).grid(row=row, column=3, sticky="w", pady=4)
        row += 1

        mono_fonts = _available_font_choices(_PREFERRED_MONO_FONTS, preferences.editor_font_family)
        ttk.Label(body, text="Editor Font").grid(row=row, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.OptionMenu(
            body,
            self._ed_font_var,
            self._ed_font_var.get(),
            *mono_fonts,
            command=lambda _v: self._refresh_preview(),
        ).grid(row=row, column=1, sticky="ew", pady=4)
        ttk.Label(body, text="Size").grid(row=row, column=2, sticky="e", padx=(12, 6), pady=4)
        ed_spin = ttk.Spinbox(
            body,
            from_=MIN_EDITOR_FONT_SIZE,
            to=MAX_EDITOR_FONT_SIZE,
            textvariable=self._ed_size_var,
            width=5,
            command=self._refresh_preview,
        )
        ed_spin.grid(row=row, column=3, sticky="w", pady=4)
        ed_spin.bind("<KeyRelease>", lambda _e: self._refresh_preview())
        row += 1

        ttk.Label(body, text="Log Font Size").grid(row=row, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Spinbox(
            body,
            from_=MIN_LOG_FONT_SIZE,
            to=MAX_LOG_FONT_SIZE,
            textvariable=self._log_size_var,
            width=5,
        ).grid(row=row, column=1, sticky="w", pady=4)
        ttk.Label(body, text="Tree Row Height").grid(row=row, column=2, sticky="e", padx=(12, 6), pady=4)
        ttk.Spinbox(
            body,
            from_=MIN_TREE_ROW_HEIGHT,
            to=MAX_TREE_ROW_HEIGHT,
            textvariable=self._row_height_var,
            width=5,
        ).grid(row=row, column=3, sticky="w", pady=4)
        row += 1

        # -- Editor & Workspace section ---------------------------------------
        ttk.Separator(body, orient=tk.HORIZONTAL).grid(row=row, column=0, columnspan=4, sticky="ew", pady=(10, 6))
        row += 1
        ttk.Label(body, text="EDITOR & WORKSPACE", style="Section.TLabel").grid(
            row=row, column=0, columnspan=4, sticky="w", pady=(0, 4)
        )
        row += 1

        ttk.Checkbutton(
            body, text="Word wrap long lines in editor", variable=self._wrap_var, command=self._refresh_preview
        ).grid(row=row, column=0, columnspan=2, sticky="w", pady=3)
        ttk.Checkbutton(
            body, text="Auto-expand Structure tree", variable=self._auto_expand_var
        ).grid(row=row, column=2, columnspan=2, sticky="w", padx=(12, 0), pady=3)
        row += 1

        ttk.Label(body, text="Default Left Panel").grid(row=row, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.OptionMenu(
            body, self._left_view_var, self._left_view_var.get(), "messages", "structure"
        ).grid(row=row, column=1, sticky="ew", pady=4)
        row += 1

        # -- Live Preview -----------------------------------------------------
        ttk.Separator(body, orient=tk.HORIZONTAL).grid(row=row, column=0, columnspan=4, sticky="ew", pady=(10, 6))
        row += 1
        ttk.Label(body, text="LIVE PREVIEW", style="Section.TLabel").grid(
            row=row, column=0, columnspan=4, sticky="w", pady=(0, 4)
        )
        row += 1

        self.preview = tk.Text(body, width=64, height=3, bd=0, padx=10, pady=8, highlightthickness=1)
        self.preview.grid(row=row, column=0, columnspan=4, sticky="ew", pady=(0, 10))
        row += 1

        # -- Action buttons ---------------------------------------------------
        btn_row = ttk.Frame(body)
        btn_row.grid(row=row, column=0, columnspan=4, sticky="ew", pady=(4, 0))
        ttk.Button(btn_row, text="Reset Defaults", style="Subtle.TButton", command=self._reset_defaults).pack(
            side=tk.LEFT
        )
        ttk.Button(btn_row, text="Save", style="Accent.TButton", command=self._save).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(btn_row, text="Apply", command=self._apply_only).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(btn_row, text="Cancel", command=self._cancel).pack(side=tk.RIGHT)

        self._refresh_preview()
        self.bind("<Escape>", lambda _e: self._cancel())
        self.grab_set()

    def build_preferences(self) -> AppPreferences:
        return AppPreferences.from_dict(
            {
                "theme": self._theme_var.get(),
                "ui_font_family": self._ui_font_var.get(),
                "ui_font_size": self._ui_size_var.get(),
                "editor_font_family": self._ed_font_var.get(),
                "editor_font_size": self._ed_size_var.get(),
                "log_font_size": self._log_size_var.get(),
                "editor_word_wrap": self._wrap_var.get(),
                "tree_row_height": self._row_height_var.get(),
                "default_left_view": self._left_view_var.get(),
                "auto_expand_structure": self._auto_expand_var.get(),
            }
        )

    def _refresh_preview(self) -> None:
        prefs = self.build_preferences()
        theme = get_theme(prefs.theme)
        border = get_border_color(theme)

        swatch_colors = (
            theme.bg,
            theme.pane_bg,
            theme.accent,
            theme.syntax_keyword,
            theme.syntax_string,
            theme.syntax_accent,
        )
        for swatch, color in zip(self._swatches, swatch_colors):
            swatch.configure(bg=color)

        self.preview.configure(
            state="normal",
            bg=theme.pane_bg,
            fg=theme.pane_fg,
            selectbackground=theme.select_bg,
            selectforeground=theme.select_fg,
            highlightbackground=border,
            highlightcolor=theme.accent,
            font=(prefs.editor_font_family, prefs.editor_font_size),
            wrap="word" if prefs.editor_word_wrap else "none",
        )
        self.preview.delete("1.0", tk.END)
        self.preview.insert("1.0", _SAMPLE_HL7)
        configure_tags(self.preview, theme)
        highlight(self.preview, "hl7")
        self.preview.configure(state="disabled")

    def _reset_defaults(self) -> None:
        defaults = AppPreferences()
        self._theme_var.set(defaults.theme)
        self._ui_font_var.set(defaults.ui_font_family)
        self._ui_size_var.set(str(defaults.ui_font_size))
        self._ed_font_var.set(defaults.editor_font_family)
        self._ed_size_var.set(str(defaults.editor_font_size))
        self._log_size_var.set(str(defaults.log_font_size))
        self._row_height_var.set(str(defaults.tree_row_height))
        self._wrap_var.set(defaults.editor_word_wrap)
        self._left_view_var.set(defaults.default_left_view)
        self._auto_expand_var.set(defaults.auto_expand_structure)
        self._refresh_preview()

    def _apply_only(self) -> None:
        prefs = self.build_preferences()
        if self._on_apply is not None:
            self._on_apply(prefs)
        self.configure(bg=get_theme(prefs.theme).bg)

    def _save(self) -> None:
        self.result = replace(self.build_preferences())
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()
