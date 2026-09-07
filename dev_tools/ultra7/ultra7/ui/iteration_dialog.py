"""Modal dialog for configuring how a highlighted message substring iterates."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ultra7.models import IterationMode, IterationSpec

_MODES: tuple[IterationMode, ...] = ("increment", "list", "timestamp")


class IterationDialog(tk.Toplevel):
    """Configures (or removes) the IterationSpec for a highlighted text range.

    Result in `self.result` (a new/updated IterationSpec) if saved, or
    `self.removed = True` if the user chose to clear the iteration field.
    """

    def __init__(
        self,
        parent: tk.Misc,
        start: int,
        end: int,
        selected_text: str,
        existing: IterationSpec | None,
    ) -> None:
        super().__init__(parent)
        self.title("Iteration Field")
        self.resizable(False, False)
        self.transient(parent)  # type: ignore[call-overload]
        self.result: IterationSpec | None = None
        self.removed = False

        self._start = start
        self._end = end

        ttk.Label(self, text="Iteration Field", font=("Rubik", 12, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 8)
        )

        preview = selected_text if len(selected_text) <= 40 else selected_text[:37] + "..."
        ttk.Label(self, text=f"Selected: {preview!r}").grid(
            row=1, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 4)
        )

        self._mode = tk.StringVar(value=existing.mode if existing else "increment")
        ttk.Label(self, text="Mode").grid(row=2, column=0, sticky="w", padx=12, pady=4)
        ttk.OptionMenu(
            self, self._mode, self._mode.get(), *_MODES, command=self._on_mode_change  # type: ignore[arg-type]
        ).grid(row=2, column=1, sticky="ew", padx=12, pady=4)

        self._step = tk.StringVar(value=str(existing.step if existing else 1))
        self._step_label = ttk.Label(self, text="Step")
        self._step_label.grid(row=3, column=0, sticky="w", padx=12, pady=4)
        self._step_entry = ttk.Entry(self, textvariable=self._step)
        self._step_entry.grid(row=3, column=1, sticky="ew", padx=12, pady=4)

        self._pad_width = tk.StringVar(value=str(existing.pad_width if existing else 0))
        self._pad_label = ttk.Label(self, text="Pad width (0 = keep original width)")
        self._pad_label.grid(row=4, column=0, sticky="w", padx=12, pady=4)
        self._pad_entry = ttk.Entry(self, textvariable=self._pad_width)
        self._pad_entry.grid(row=4, column=1, sticky="ew", padx=12, pady=4)

        self._values_label = ttk.Label(self, text="Values (one per line, cycled in order)")
        self._values_label.grid(row=5, column=0, columnspan=2, sticky="w", padx=12, pady=(8, 0))
        self._values_box = tk.Text(self, width=36, height=5, font=("Menlo", 10), bd=1, relief="solid")
        if existing and existing.mode == "list":
            self._values_box.insert("1.0", "\n".join(existing.values))
        self._values_box.grid(row=6, column=0, columnspan=2, sticky="ew", padx=12, pady=4)

        self._timestamp_format = tk.StringVar(
            value=existing.timestamp_format if existing else "%Y%m%d%H%M%S"
        )
        self._timestamp_label = ttk.Label(self, text="strftime format")
        self._timestamp_label.grid(row=7, column=0, sticky="w", padx=12, pady=4)
        self._timestamp_entry = ttk.Entry(self, textvariable=self._timestamp_format)
        self._timestamp_entry.grid(row=7, column=1, sticky="ew", padx=12, pady=4)

        ttk.Separator(self, orient=tk.HORIZONTAL).grid(
            row=8, column=0, columnspan=2, sticky="ew", padx=12, pady=(8, 0)
        )
        button_row = ttk.Frame(self)
        button_row.grid(row=9, column=0, columnspan=2, pady=12)
        if existing is not None:
            ttk.Button(button_row, text="Remove", command=self._remove).pack(side=tk.LEFT, padx=4)
        ttk.Button(button_row, text="Cancel", command=self._cancel).pack(side=tk.LEFT, padx=4)
        ttk.Button(button_row, text="Save", command=self._save).pack(side=tk.LEFT, padx=4)

        self._on_mode_change(self._mode.get())
        self.grab_set()
        self._mode.set(self._mode.get())  # force validation
        self.after(100, self._step_entry.focus_set)

    def _on_mode_change(self, mode: str) -> None:
        increment_state = "normal" if mode == "increment" else "disabled"
        for widget in (self._step_label, self._step_entry, self._pad_label, self._pad_entry):
            widget.configure(state=increment_state)
        list_state = "normal" if mode == "list" else "disabled"
        self._values_label.configure(state=list_state)
        self._values_box.configure(state=list_state)  # type: ignore[call-overload]
        timestamp_state = "normal" if mode == "timestamp" else "disabled"
        self._timestamp_label.configure(state=timestamp_state)
        self._timestamp_entry.configure(state=timestamp_state)

    def _save(self) -> None:
        mode = self._mode.get()
        try:
            step = int(self._step.get())
        except ValueError:
            step = 1
        try:
            pad_width = int(self._pad_width.get())
        except ValueError:
            pad_width = 0
        values = [line.strip() for line in self._values_box.get("1.0", tk.END).splitlines() if line.strip()]

        self.result = IterationSpec(
            start=self._start,
            end=self._end,
            mode=mode,  # type: ignore[arg-type]
            step=step,
            pad_width=pad_width,
            values=values,
            timestamp_format=self._timestamp_format.get() or "%Y%m%d%H%M%S",
        )
        self.destroy()

    def _remove(self) -> None:
        self.removed = True
        self.destroy()

    def _cancel(self) -> None:
        self.destroy()
