"""Message list + text editor pane, with format detection and syntax highlighting."""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from ultra7.formats.detect import detect_format
from ultra7.formats.highlighting import configure_tags, highlight
from ultra7.formats.pretty_print import pretty_print
from ultra7.models import IterationSpec, Message, MessageFormat
from ultra7.ui.iteration_dialog import IterationDialog
from ultra7.ui.themes import DEFAULT_THEME_NAME, Theme, get_theme

_FORMATS: tuple[MessageFormat, ...] = ("hl7", "xml", "json")
_ITERATE_TAG = "iterate-field"
_ITERATE_BG = "#F8CA4D"
_DISABLED_FG = "#6B7280"  # muted grey, legible on both light and dark themes


class EditorPane(ttk.Frame):
    """Owns the ordered message list for the active project and its text editor."""

    def __init__(self, parent: tk.Misc, on_change: Callable[[], None]) -> None:
        super().__init__(parent)
        self._on_change = on_change
        self._messages: list[Message] = []
        self._selected_index: int | None = None
        self._suspend_events = False

        left = ttk.Frame(self)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 4))

        listbox_frame = ttk.Frame(left)
        listbox_frame.pack(fill=tk.BOTH, expand=True)
        self.listbox = tk.Listbox(listbox_frame, exportselection=False, width=28, selectmode=tk.EXTENDED)
        listbox_scrollbar = ttk.Scrollbar(listbox_frame, orient=tk.VERTICAL, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=listbox_scrollbar.set)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        listbox_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.bind("<<ListboxSelect>>", self._handle_select)

        list_buttons = ttk.Frame(left)
        list_buttons.pack(fill=tk.X)
        ttk.Button(list_buttons, text="New", command=self._new_message).grid(row=0, column=0, sticky="ew")
        ttk.Button(list_buttons, text="Delete", command=self._delete_message).grid(row=0, column=1, sticky="ew")
        ttk.Button(list_buttons, text="▲", width=3, command=lambda: self._move(-1)).grid(row=1, column=0, sticky="ew")
        ttk.Button(list_buttons, text="▼", width=3, command=lambda: self._move(1)).grid(row=1, column=1, sticky="ew")
        self._toggle_enabled_btn = ttk.Button(
            list_buttons, text="Disable", command=self._toggle_message_enabled, state="disabled"
        )
        self._toggle_enabled_btn.grid(row=2, column=0, columnspan=2, sticky="ew")
        ttk.Button(left, text="Load from disk…", command=self._load_from_disk).pack(fill=tk.X, pady=(4, 0))

        right = ttk.Frame(self)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        toolbar = ttk.Frame(right)
        toolbar.pack(fill=tk.X)
        ttk.Label(toolbar, text="Name").pack(side=tk.LEFT)
        self._name_var = tk.StringVar()
        name_entry = ttk.Entry(toolbar, textvariable=self._name_var, width=20)
        name_entry.pack(side=tk.LEFT, padx=(2, 8))
        name_entry.bind("<KeyRelease>", self._handle_name_change)

        ttk.Label(toolbar, text="Format").pack(side=tk.LEFT)
        self._format_var = tk.StringVar(value="hl7")
        format_menu = ttk.OptionMenu(
            toolbar, self._format_var, "hl7", *_FORMATS, command=self._handle_format_change  # type: ignore[arg-type]
        )
        format_menu.pack(side=tk.LEFT, padx=(2, 8))

        ttk.Button(toolbar, text="Format", command=self._format_message).pack(side=tk.LEFT, padx=(2, 8))

        iter_row = ttk.Frame(right)
        iter_row.pack(fill=tk.X, pady=(2, 0))
        ttk.Button(iter_row, text="Mark Iterate Field", command=self._mark_iteration_field).pack(side=tk.LEFT)
        self._edit_iter_btn = ttk.Button(
            iter_row, text="Edit Iterate Field…", command=self._edit_iteration_field, state="disabled"
        )
        self._edit_iter_btn.pack(side=tk.LEFT, padx=(4, 0))
        self._iteration_status_var = tk.StringVar(value="No iteration field set")
        ttk.Label(iter_row, textvariable=self._iteration_status_var).pack(side=tk.LEFT, padx=(8, 0))

        self.text = tk.Text(right, wrap="none", undo=True)
        configure_tags(self.text, get_theme(DEFAULT_THEME_NAME))
        self.text.tag_configure(_ITERATE_TAG, background=_ITERATE_BG)
        self.text.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        self.text.bind("<<Modified>>", self._handle_text_modified)

        self._set_editor_enabled(False)

    def apply_theme(self, theme: Theme) -> None:
        """Re-colour syntax highlighting tags for the given theme (ranges are untouched)."""
        configure_tags(self.text, theme)

    # -- project wiring ----------------------------------------------------

    def set_messages(self, messages: list[Message]) -> None:
        self._messages = list(messages)
        self._selected_index = None
        self._refresh_listbox()
        self._clear_editor()

    def get_messages(self) -> list[Message]:
        return list(self._messages)

    def get_selected_messages(self) -> list[Message]:
        """All messages currently highlighted in the list (supports multi-select)."""
        self._commit_current_edits()
        return [self._messages[i] for i in self.listbox.curselection()]

    # -- list management -----------------------------------------------------

    def _refresh_listbox(self, select: int | None = None) -> None:
        self._populate_listbox_rows()
        if select is not None and 0 <= select < len(self._messages):
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(select)
            self._load_into_editor(select)

    def _populate_listbox_rows(self) -> None:
        self.listbox.delete(0, tk.END)
        for index, msg in enumerate(self._messages):
            prefix = "" if msg.enabled else "[off] "
            self.listbox.insert(tk.END, f"{prefix}{msg.name}")
            if not msg.enabled:
                self.listbox.itemconfig(index, foreground=_DISABLED_FG)

    def _new_message(self) -> None:
        self._commit_current_edits()
        message = Message(name=f"Message {len(self._messages) + 1}", format="hl7", content="")
        self._messages.append(message)
        self._refresh_listbox(select=len(self._messages) - 1)
        self._on_change()

    def _delete_message(self) -> None:
        if self._selected_index is None:
            return
        del self._messages[self._selected_index]
        self._selected_index = None
        self._refresh_listbox()
        self._clear_editor()
        self._on_change()

    def _move(self, offset: int) -> None:
        if self._selected_index is None:
            return
        new_index = self._selected_index + offset
        if not (0 <= new_index < len(self._messages)):
            return
        self._messages[self._selected_index], self._messages[new_index] = (
            self._messages[new_index],
            self._messages[self._selected_index],
        )
        self._refresh_listbox(select=new_index)
        self._on_change()

    def _load_from_disk(self) -> None:
        path = filedialog.askopenfilename(title="Load message")
        if not path:
            return
        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.read()
        name = path.rsplit("/", 1)[-1]
        message = Message(name=name, format=detect_format(content), content=content)
        self._messages.append(message)
        self._refresh_listbox(select=len(self._messages) - 1)
        self._on_change()

    # -- selection / editor sync --------------------------------------------

    def _handle_select(self, _event: tk.Event) -> None:
        if not self.listbox.curselection():
            return
        active_index = self.listbox.index(tk.ACTIVE)
        if 0 <= active_index < len(self._messages):
            self._commit_current_edits()
            self._load_into_editor(active_index)
        self._update_toggle_enabled_button_for_selection()

    def _load_into_editor(self, index: int) -> None:
        self._suspend_events = True
        message = self._messages[index]
        self._selected_index = index
        self._name_var.set(message.name)
        self._format_var.set(message.format)
        # Must enable before writing — Tk silently ignores edits on a disabled Text widget.
        self._set_editor_enabled(True)
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", message.content)
        self.text.edit_modified(False)
        highlight(self.text, message.format)
        self._apply_iteration_tag(message)
        self._update_iteration_label(message)
        self._update_toggle_enabled_button_for_selection()
        self._suspend_events = False

    def _clear_editor(self) -> None:
        self._suspend_events = True
        self._name_var.set("")
        self.text.delete("1.0", tk.END)
        self.text.edit_modified(False)
        self._set_editor_enabled(False)
        self._iteration_status_var.set("No iteration field set")
        self._edit_iter_btn.configure(state="disabled")
        self._toggle_enabled_btn.configure(text="Disable", state="disabled")
        self._suspend_events = False

    def _set_editor_enabled(self, enabled: bool) -> None:
        self.text.configure(state="normal" if enabled else "disabled")

    def _char_offset(self, index: object) -> int:
        """Convert a Tk text index (e.g. 'sel.first') to an absolute character offset."""
        result = self.text.count("1.0", index, "chars")  # type: ignore[call-overload]
        return result[0] if result else 0

    def _commit_current_edits(self) -> None:
        if self._selected_index is None or self._suspend_events:
            return
        message = self._messages[self._selected_index]
        message.content = self.text.get("1.0", "end-1c")
        if message.iteration is not None:
            # Tk shifts the tag as surrounding text changes; resync our stored offsets.
            ranges = self.text.tag_ranges(_ITERATE_TAG)
            if ranges:
                message.iteration.start = self._char_offset(ranges[0])
                message.iteration.end = self._char_offset(ranges[1])
            else:
                message.iteration = None
            self._update_iteration_label(message)

    # -- field change handlers ----------------------------------------------

    def _handle_name_change(self, _event: tk.Event) -> None:
        if self._selected_index is None or self._suspend_events:
            return
        self._messages[self._selected_index].name = self._name_var.get()
        current_selection = self._selected_index
        self._refresh_listbox(select=current_selection)
        self._on_change()

    def _handle_format_change(self, value: str) -> None:
        if self._selected_index is None:
            return
        self._messages[self._selected_index].format = value  # type: ignore[assignment]
        highlight(self.text, value)  # type: ignore[arg-type]
        self._on_change()

    def _toggle_message_enabled(self) -> None:
        """Bulk-toggle every selected message: disable all if any are enabled, else enable all."""
        indices = self.listbox.curselection()
        if not indices:
            return
        selected_messages = [self._messages[i] for i in indices]
        new_state = not any(m.enabled for m in selected_messages)
        for message in selected_messages:
            message.enabled = new_state
        self._populate_listbox_rows()
        for i in indices:
            self.listbox.selection_set(i)
        self._update_toggle_enabled_button_for_selection()
        self._on_change()

    def _update_toggle_enabled_button_for_selection(self) -> None:
        indices = self.listbox.curselection()
        if not indices:
            self._toggle_enabled_btn.configure(text="Disable", state="disabled")
            return
        any_enabled = any(self._messages[i].enabled for i in indices)
        self._toggle_enabled_btn.configure(text="Disable" if any_enabled else "Enable", state="normal")

    def _format_message(self) -> None:
        if self._selected_index is None:
            return
        self._commit_current_edits()
        message = self._messages[self._selected_index]
        try:
            formatted = pretty_print(message.content, message.format)
        except ValueError as exc:
            messagebox.showerror("Ultra7", str(exc))
            return

        # Reformatting shifts character positions — try to relocate the marked
        # substring by its text; if it can't be found unambiguously, clear it.
        if message.iteration is not None:
            marked_text = message.content[message.iteration.start : message.iteration.end]
            new_start = formatted.find(marked_text) if marked_text else -1
            if new_start >= 0 and formatted.count(marked_text) == 1:
                message.iteration.start = new_start
                message.iteration.end = new_start + len(marked_text)
            else:
                message.iteration = None
                messagebox.showinfo(
                    "Ultra7", "Formatting cleared the iteration field — its marked text could not be relocated."
                )

        message.content = formatted
        self._load_into_editor(self._selected_index)
        self._on_change()

    def _handle_text_modified(self, _event: tk.Event) -> None:
        if self._suspend_events or self._selected_index is None:
            return
        if not self.text.edit_modified():
            return
        self._commit_current_edits()
        highlight(self.text, self._format_var.get())  # type: ignore[arg-type]
        self.text.edit_modified(False)
        self._on_change()

    # -- iteration field ------------------------------------------------------

    def _mark_iteration_field(self) -> None:
        """Mark the current text selection as the message's iteration field."""
        if self._selected_index is None:
            return
        ranges = self.text.tag_ranges("sel")
        if not ranges:
            messagebox.showinfo("Ultra7", "Highlight part of the message text first.")
            return
        start_idx, end_idx = ranges[0], ranges[1]
        start_off = self._char_offset(start_idx)
        end_off = self._char_offset(end_idx)
        if start_off == end_off:
            return

        message = self._messages[self._selected_index]
        selected_text = self.text.get(start_idx, end_idx)
        existing = message.iteration
        # Only reuse the previous config as defaults if it's the same range.
        if existing is not None and (existing.start != start_off or existing.end != end_off):
            existing = None
        self._run_iteration_dialog(message, start_off, end_off, selected_text, existing)

    def _edit_iteration_field(self) -> None:
        """Edit (or remove) the message's existing iteration field, no selection needed."""
        if self._selected_index is None:
            return
        message = self._messages[self._selected_index]
        if message.iteration is None:
            messagebox.showinfo("Ultra7", "No iteration field set for this message.")
            return
        start_off, end_off = message.iteration.start, message.iteration.end
        selected_text = self.text.get(f"1.0+{start_off}c", f"1.0+{end_off}c")
        self._run_iteration_dialog(message, start_off, end_off, selected_text, message.iteration)

    def _run_iteration_dialog(
        self, message: Message, start_off: int, end_off: int, selected_text: str, existing: IterationSpec | None
    ) -> None:
        dialog = IterationDialog(self, start_off, end_off, selected_text, existing)
        self.wait_window(dialog)

        if dialog.removed:
            message.iteration = None
        elif dialog.result is not None:
            message.iteration = dialog.result
        else:
            return
        self._apply_iteration_tag(message)
        self._update_iteration_label(message)
        self._on_change()

    def _apply_iteration_tag(self, message: Message) -> None:
        self.text.tag_remove(_ITERATE_TAG, "1.0", tk.END)
        if message.iteration is None:
            return
        start_idx = f"1.0+{message.iteration.start}c"
        end_idx = f"1.0+{message.iteration.end}c"
        self.text.tag_add(_ITERATE_TAG, start_idx, end_idx)

    def _update_iteration_label(self, message: Message) -> None:
        spec = message.iteration
        if spec is None:
            self._iteration_status_var.set("No iteration field set")
            self._edit_iter_btn.configure(state="disabled")
            return
        self._edit_iter_btn.configure(state="normal")
        if spec.mode == "increment":
            self._iteration_status_var.set(f"Iterates: increment (step {spec.step})")
        elif spec.mode == "list":
            self._iteration_status_var.set(f"Iterates: list ({len(spec.values)} values)")
        else:
            self._iteration_status_var.set(f"Iterates: timestamp ({spec.timestamp_format})")
