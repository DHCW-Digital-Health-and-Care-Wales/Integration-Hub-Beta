"""Dialogs for configuring and managing message iteration fields."""
from __future__ import annotations

import random
import tkinter as tk
from tkinter import ttk
from typing import Callable

from ultra7.iteration import apply_iteration
from ultra7.models import IterationMode, IterationSpec
from ultra7.ui.themes import DEFAULT_THEME_NAME, Theme, get_border_color, get_semantic_colors, get_theme

_MODES: tuple[IterationMode, ...] = ("increment", "list", "timestamp", "nhs_number")

_MODE_LABELS: dict[IterationMode, str] = {
    "increment": "Increment integer (add step each repeat)",
    "list": "Cycle through a list of values",
    "timestamp": "Current timestamp (strftime)",
    "nhs_number": "Generate valid Mod-11 NHS Number",
}
_LABEL_TO_MODE: dict[str, IterationMode] = {label: mode for mode, label in _MODE_LABELS.items()}

_TIMESTAMP_PRESETS: tuple[tuple[str, str], ...] = (
    ("HL7", "%Y%m%d%H%M%S"),
    ("ISO", "%Y-%m-%dT%H:%M:%S"),
    ("Date", "%Y%m%d"),
)


class IterationDialog(tk.Toplevel):
    """Configures (or removes) the IterationSpec for a highlighted text range.

    Shows only the controls relevant to the selected mode plus a live Send #1/#2/#3
    preview and inline validation warnings.
    """

    def __init__(
        self,
        parent: tk.Misc,
        start: int,
        end: int,
        selected_text: str,
        existing: IterationSpec | None = None,
        theme: Theme | None = None,
    ) -> None:
        super().__init__(parent)
        self.title("Iteration Field")
        self.resizable(False, False)
        self.transient(parent)  # type: ignore[call-overload]
        self.result: IterationSpec | None = None
        self.removed = False
        self._theme = theme or get_theme(DEFAULT_THEME_NAME)
        self.configure(bg=self._theme.bg)

        self._start = start
        self._end = end
        self._selected_text = selected_text

        body = ttk.Frame(self, padding=14)
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(1, weight=1)

        ttk.Label(body, text="Iteration Field", font=("Rubik", 12, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 4)
        )
        ttk.Label(
            body,
            text="Recomputes the marked substring on each repeat when Repeat > 1.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 8))

        preview = selected_text if len(selected_text) <= 44 else selected_text[:41] + "…"
        ttk.Label(body, text="Marked text", style="Muted.TLabel").grid(
            row=2, column=0, sticky="w", padx=(0, 10), pady=4
        )
        ttk.Label(body, text=repr(preview), font=("Menlo", 10, "bold")).grid(row=2, column=1, sticky="w", pady=4)

        # Default mode: pick increment if text is an integer, else list so it works immediately.
        default_mode: IterationMode = (
            existing.mode if existing else ("increment" if selected_text.strip().lstrip("+-").isdigit() else "list")
        )
        self._mode_label = tk.StringVar(value=_MODE_LABELS[default_mode])
        ttk.Label(body, text="Mode").grid(row=3, column=0, sticky="w", padx=(0, 10), pady=4)
        mode_combo = ttk.Combobox(
            body,
            textvariable=self._mode_label,
            values=tuple(_MODE_LABELS.values()),
            state="readonly",
            width=36,
        )
        mode_combo.grid(row=3, column=1, sticky="ew", pady=4)
        mode_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_mode_change())

        # -- Increment fields -------------------------------------------------
        self._step = tk.StringVar(value=str(existing.step if existing else 1))
        self._step_label = ttk.Label(body, text="Step")
        self._step_entry = ttk.Entry(body, textvariable=self._step)
        self._step_entry.bind("<KeyRelease>", lambda _e: self._refresh_preview())

        self._pad_width = tk.StringVar(value=str(existing.pad_width if existing else 0))
        self._pad_label = ttk.Label(body, text="Pad width (0 = keep width)")
        self._pad_entry = ttk.Entry(body, textvariable=self._pad_width)
        self._pad_entry.bind("<KeyRelease>", lambda _e: self._refresh_preview())

        # -- List fields ------------------------------------------------------
        self._values_label = ttk.Label(body, text="Values (one per line, cycled in order)")
        self._values_box = tk.Text(
            body,
            width=40,
            height=5,
            font=("Menlo", 10),
            bd=0,
            padx=8,
            pady=6,
            highlightthickness=1,
            bg=self._theme.pane_bg,
            fg=self._theme.pane_fg,
            insertbackground=self._theme.pane_fg,
            selectbackground=self._theme.select_bg,
            selectforeground=self._theme.select_fg,
            highlightbackground=get_border_color(self._theme),
            highlightcolor=self._theme.accent,
        )
        if existing and existing.mode == "list":
            self._values_box.insert("1.0", "\n".join(existing.values))
        elif not existing and selected_text:
            self._values_box.insert("1.0", f"{selected_text}\n")
        self._values_box.bind("<KeyRelease>", lambda _e: self._refresh_preview())

        # -- Timestamp fields -------------------------------------------------
        self._timestamp_format = tk.StringVar(
            value=existing.timestamp_format if existing else "%Y%m%d%H%M%S"
        )
        self._timestamp_label = ttk.Label(body, text="strftime format")
        self._timestamp_entry = ttk.Entry(body, textvariable=self._timestamp_format)
        self._timestamp_entry.bind("<KeyRelease>", lambda _e: self._refresh_preview())

        self._ts_preset_row = ttk.Frame(body)
        ttk.Label(self._ts_preset_row, text="Presets:", style="Muted.TLabel").pack(side=tk.LEFT, padx=(0, 6))
        for label, fmt in _TIMESTAMP_PRESETS:
            ttk.Button(
                self._ts_preset_row,
                text=label,
                style="Subtle.TButton",
                command=lambda f=fmt: self._set_timestamp_format(f),  # type: ignore[misc]
            ).pack(side=tk.LEFT, padx=(0, 4))

        # -- NHS Number hint --------------------------------------------------
        self._nhs_hint = ttk.Label(
            body,
            text="Generates valid synthetic 10-digit Mod-11 UK NHS Numbers (999… test range).\n"
            "Preserves spacing automatically if the marked text contains spaces.",
            style="Muted.TLabel",
            justify=tk.LEFT,
        )

        # -- Live Example Preview + Validation --------------------------------
        ttk.Separator(body, orient=tk.HORIZONTAL).grid(row=9, column=0, columnspan=2, sticky="ew", pady=(10, 6))
        ttk.Label(body, text="EXAMPLE OUTPUT", style="Section.TLabel").grid(
            row=10, column=0, columnspan=2, sticky="w", pady=(0, 2)
        )
        self._preview_var = tk.StringVar(value="")
        self._preview_label = ttk.Label(
            body, textvariable=self._preview_var, font=("Menlo", 10), wraplength=420, justify=tk.LEFT
        )
        self._preview_label.grid(row=11, column=0, columnspan=2, sticky="w", pady=(0, 4))

        self._warning_var = tk.StringVar(value="")
        self._warning_label = ttk.Label(body, textvariable=self._warning_var, wraplength=420, justify=tk.LEFT)
        self._warning_label.grid(row=12, column=0, columnspan=2, sticky="w", pady=(0, 4))

        ttk.Separator(body, orient=tk.HORIZONTAL).grid(row=13, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        button_row = ttk.Frame(body)
        button_row.grid(row=14, column=0, columnspan=2, pady=(10, 0))
        if existing is not None:
            ttk.Button(button_row, text="Remove", style="Danger.TButton", command=self._remove).pack(
                side=tk.LEFT, padx=4
            )
        ttk.Button(button_row, text="Cancel", command=self._cancel).pack(side=tk.LEFT, padx=4)
        self._save_btn = ttk.Button(button_row, text="Save", style="Accent.TButton", command=self._save)
        self._save_btn.pack(side=tk.LEFT, padx=4)

        self._on_mode_change()
        self.bind("<Escape>", lambda _e: self._cancel())
        self.lift()
        self.focus_set()

    def _current_mode(self) -> IterationMode:
        return _LABEL_TO_MODE.get(self._mode_label.get(), "increment")

    def _set_timestamp_format(self, fmt: str) -> None:
        self._timestamp_format.set(fmt)
        self._refresh_preview()

    def _on_mode_change(self) -> None:
        mode = self._current_mode()
        for widget in (
            self._step_label,
            self._step_entry,
            self._pad_label,
            self._pad_entry,
            self._values_label,
            self._values_box,
            self._timestamp_label,
            self._timestamp_entry,
            self._ts_preset_row,
            self._nhs_hint,
        ):
            widget.grid_remove()

        if mode == "increment":
            self._step_label.grid(row=4, column=0, sticky="w", padx=(0, 10), pady=4)
            self._step_entry.grid(row=4, column=1, sticky="ew", pady=4)
            self._pad_label.grid(row=5, column=0, sticky="w", padx=(0, 10), pady=4)
            self._pad_entry.grid(row=5, column=1, sticky="ew", pady=4)
        elif mode == "list":
            self._values_label.grid(row=4, column=0, columnspan=2, sticky="w", pady=(6, 2))
            self._values_box.grid(row=5, column=0, columnspan=2, sticky="ew", pady=4)
        elif mode == "timestamp":
            self._timestamp_label.grid(row=4, column=0, sticky="w", padx=(0, 10), pady=4)
            self._timestamp_entry.grid(row=4, column=1, sticky="ew", pady=4)
            self._ts_preset_row.grid(row=5, column=0, columnspan=2, sticky="w", pady=(2, 4))
        else:
            self._nhs_hint.grid(row=4, column=0, columnspan=2, sticky="w", pady=(6, 4))

        self._refresh_preview()

    def _build_spec(self) -> tuple[IterationSpec, str | None]:
        mode = self._current_mode()
        warning: str | None = None

        try:
            step = int(self._step.get())
        except ValueError:
            step = 1
            if mode == "increment":
                warning = "Step must be a whole number (e.g. 1 or 10)."

        try:
            pad_width = max(0, int(self._pad_width.get()))
        except ValueError:
            pad_width = 0
            if mode == "increment" and warning is None:
                warning = "Pad width must be 0 or a positive integer."

        values = [line.strip() for line in self._values_box.get("1.0", tk.END).splitlines() if line.strip()]
        ts_fmt = self._timestamp_format.get().strip() or "%Y%m%d%H%M%S"

        if mode == "increment" and warning is None:
            try:
                int(self._selected_text)
            except ValueError:
                warning = (
                    f"Marked text {self._selected_text!r} is not an integer — "
                    "increment mode requires digits (or switch to list / timestamp / nhs_number)."
                )
        elif mode == "list" and not values:
            warning = "Enter at least one value (one per line) to cycle through."

        spec = IterationSpec(
            start=self._start,
            end=self._end,
            mode=mode,
            step=step,
            pad_width=pad_width,
            values=values,
            timestamp_format=ts_fmt,
        )
        return spec, warning

    def _refresh_preview(self) -> None:
        spec, warning = self._build_spec()
        colors = get_semantic_colors(self._theme)
        if warning:
            self._warning_label.configure(foreground=colors["error"])
            self._warning_var.set(f"⚠ {warning}")
            self._preview_var.set("")
            return

        self._warning_var.set("")
        # Preview against a dummy single-span string using the marked text directly.
        preview_spec = IterationSpec(
            start=0,
            end=len(self._selected_text),
            mode=spec.mode,
            step=spec.step,
            pad_width=spec.pad_width,
            values=spec.values,
            timestamp_format=spec.timestamp_format,
        )
        rng = random.Random(42)  # nosec B311 - deterministic preview
        samples = [
            f"#{idx + 1}: {apply_iteration(self._selected_text, preview_spec, idx, rng=rng)}"
            for idx in range(3)
        ]
        self._preview_var.set("   |   ".join(samples))

    def _save(self) -> None:
        spec, warning = self._build_spec()
        if warning:
            colors = get_semantic_colors(self._theme)
            self._warning_label.configure(foreground=colors["error"])
            self._warning_var.set(f"⚠ {warning}")
            return
        self.result = spec
        self.destroy()

    def _remove(self) -> None:
        self.removed = True
        self.destroy()

    def _cancel(self) -> None:
        self.destroy()


class ManageIterationsDialog(tk.Toplevel):
    """Lists all iteration fields on the active message with Edit, Jump, Remove, and Clear All."""

    def __init__(
        self,
        parent: tk.Misc,
        content: str,
        specs: list[IterationSpec],
        on_edit: Callable[[IterationSpec], None],
        on_jump: Callable[[IterationSpec], None],
        on_remove: Callable[[IterationSpec], None],
        on_clear_all: Callable[[], None],
        theme: Theme | None = None,
    ) -> None:
        super().__init__(parent)
        self.title("Manage Iteration Fields")
        self.geometry("680x360")
        self.transient(parent)  # type: ignore[call-overload]
        self._content = content
        self._specs = list(specs)
        self._on_edit = on_edit
        self._on_jump = on_jump
        self._on_remove = on_remove
        self._on_clear_all = on_clear_all
        self._theme = theme or get_theme(DEFAULT_THEME_NAME)
        self.configure(bg=self._theme.bg)

        body = ttk.Frame(self, padding=14)
        body.pack(fill=tk.BOTH, expand=True)

        ttk.Label(body, text="Iteration Fields on This Message", font=("Rubik", 12, "bold")).pack(
            anchor="w", pady=(0, 6)
        )

        tree_frame = ttk.Frame(body)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            tree_frame,
            columns=("text", "mode", "example"),
            show="headings",
            selectmode="browse",
        )
        self.tree.heading("text", text="Marked Text", anchor="w")
        self.tree.heading("mode", text="Mode", anchor="w")
        self.tree.heading("example", text="Example (#1 → #2)", anchor="w")
        self.tree.column("text", width=150, stretch=True)
        self.tree.column("mode", width=150, stretch=True)
        self.tree.column("example", width=280, stretch=True)

        scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<Double-1>", lambda _e: self._handle_edit())

        btn_row = ttk.Frame(body)
        btn_row.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(btn_row, text="Edit…", style="Accent.TButton", command=self._handle_edit).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        ttk.Button(btn_row, text="Jump to Text", command=self._handle_jump).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_row, text="Remove", style="Danger.TButton", command=self._handle_remove).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        ttk.Button(btn_row, text="Clear All", style="Danger.TButton", command=self._handle_clear_all).pack(
            side=tk.LEFT
        )
        ttk.Button(btn_row, text="Close", command=self.destroy).pack(side=tk.RIGHT)

        self._item_to_spec: dict[str, IterationSpec] = {}
        self.refresh(content, specs)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.lift()
        self.focus_set()

    def refresh(self, content: str, specs: list[IterationSpec]) -> None:
        self._content = content
        self._specs = list(specs)
        self.tree.delete(*self.tree.get_children())
        self._item_to_spec.clear()
        rng = random.Random(42)  # nosec B311 - deterministic preview
        for spec in self._specs:
            snippet = content[spec.start : spec.end]
            preview_spec = IterationSpec(
                start=0,
                end=len(snippet),
                mode=spec.mode,
                step=spec.step,
                pad_width=spec.pad_width,
                values=spec.values,
                timestamp_format=spec.timestamp_format,
            )
            s1 = apply_iteration(snippet, preview_spec, 0, rng=rng)
            s2 = apply_iteration(snippet, preview_spec, 1, rng=rng)
            item_id = self.tree.insert("", tk.END, values=(snippet, spec.mode, f"{s1}  →  {s2}"))
            self._item_to_spec[item_id] = spec
        children = self.tree.get_children()
        if children:
            self.tree.selection_set(children[0])

    def _selected_spec(self) -> IterationSpec | None:
        sel = self.tree.selection()
        if not sel:
            return None
        return self._item_to_spec.get(sel[0])

    def _handle_edit(self) -> None:
        spec = self._selected_spec()
        if spec is not None:
            self.destroy()
            self._on_edit(spec)

    def _handle_jump(self) -> None:
        spec = self._selected_spec()
        if spec is not None:
            self._on_jump(spec)

    def _handle_remove(self) -> None:
        spec = self._selected_spec()
        if spec is not None:
            self._on_remove(spec)
            remaining = [s for s in self._specs if s is not spec]
            if not remaining:
                self.destroy()
            else:
                self.refresh(self._content, remaining)

    def _handle_clear_all(self) -> None:
        self._on_clear_all()
        self.destroy()
