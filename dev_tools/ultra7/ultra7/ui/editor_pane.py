"""Message list + text editor pane, with format detection and syntax highlighting."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Literal

from ultra7.anonymise import anonymise_message
from ultra7.formats.detect import detect_format
from ultra7.formats.highlighting import configure_tags, highlight
from ultra7.formats.pretty_print import pretty_print
from ultra7.formats.structure import (
    StructureNode,
    filter_structure_nodes,
    find_deepest_node,
    parse_structure,
)
from ultra7.models import IterationSpec, Message, MessageFormat
from ultra7.settings import AppPreferences
from ultra7.ui.iteration_dialog import IterationDialog, ManageIterationsDialog
from ultra7.ui.preview_dialog import IterationPreviewDialog
from ultra7.ui.themes import (
    DEFAULT_THEME_NAME,
    Theme,
    get_border_color,
    get_semantic_colors,
    get_theme,
    is_dark_theme,
)

LeftViewMode = Literal["messages", "structure"]

_FORMATS: tuple[MessageFormat, ...] = ("hl7", "xml", "json")
_ITERATE_TAG_PREFIX = "iterate-field-"
_STRUCTURE_SYNC_TAG = "structure-sync"
_FIND_MATCH_TAG = "find-match"
_FIND_CURRENT_TAG = "find-current"
_ITERATE_BG = "#F8CA4D"
_ITERATE_FG = "#1B294A"
_DISABLED_FG = "#6B7280"  # muted grey, legible on both light and dark themes
_LEFT_PANE_WIDTH = 300


class EditorPane(ttk.Frame):
    """Owns the left panel (message list or structure tree) and the text editor."""

    def __init__(self, parent: tk.Misc, on_change: Callable[[], None]) -> None:
        super().__init__(parent)
        self._on_change = on_change
        self._messages: list[Message] = []
        self._selected_index: int | None = None
        self._suspend_events = False
        self._ignore_tree_select_item: str | None = None
        self._left_view: LeftViewMode = "messages"
        self._tree_nodes: list[StructureNode] = []
        self._tree_nodes_by_item: dict[str, StructureNode] = {}
        self._span_to_item: dict[tuple[int, int], str] = {}
        self._inline_editor: ttk.Entry | None = None
        self._find_matches: list[tuple[int, int]] = []
        self._find_index: int = -1
        self._iter_tag_count: int = 0
        self._iter_dialog: IterationDialog | None = None
        self._manage_iter_dialog: ManageIterationsDialog | None = None
        self._current_path: str = ""
        self._auto_expand_structure: bool = False
        self._theme: Theme = get_theme(DEFAULT_THEME_NAME)

        self._paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self._paned.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(self._paned)
        self._paned.add(left, weight=0)

        # Mode switcher for the left panel: Messages list vs Structure tree.
        mode_bar = ttk.Frame(left)
        mode_bar.pack(fill=tk.X, padx=(8, 4), pady=(6, 6))
        mode_bar.columnconfigure(0, weight=1)
        mode_bar.columnconfigure(1, weight=1)
        self._messages_mode_btn = ttk.Button(
            mode_bar,
            text="Messages",
            style="Accent.TButton",
            command=lambda: self.set_left_view("messages"),
        )
        self._structure_mode_btn = ttk.Button(
            mode_bar,
            text="Structure",
            command=lambda: self.set_left_view("structure"),
        )
        self._messages_mode_btn.grid(row=0, column=0, sticky="ew", padx=(0, 2))
        self._structure_mode_btn.grid(row=0, column=1, sticky="ew", padx=(2, 0))

        # -- Messages panel ---------------------------------------------------
        self._messages_panel = ttk.Frame(left)
        self._messages_panel.pack(fill=tk.BOTH, expand=True, padx=(8, 4), pady=(0, 4))

        listbox_frame = ttk.Frame(self._messages_panel)
        listbox_frame.pack(fill=tk.BOTH, expand=True)
        self.listbox = tk.Listbox(
            listbox_frame,
            exportselection=False,
            width=26,
            selectmode=tk.EXTENDED,
            font=("Rubik", 10),
            activestyle="none",
            bd=0,
            highlightthickness=1,
        )
        listbox_scrollbar = ttk.Scrollbar(listbox_frame, orient=tk.VERTICAL, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=listbox_scrollbar.set)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        listbox_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.bind("<<ListboxSelect>>", self._handle_select)

        list_buttons = ttk.Frame(self._messages_panel)
        list_buttons.pack(fill=tk.X, pady=(6, 0))
        list_buttons.columnconfigure(0, weight=1)
        list_buttons.columnconfigure(1, weight=1)
        ttk.Button(list_buttons, text="+ New", command=self._new_message).grid(
            row=0, column=0, sticky="ew", padx=(0, 3)
        )
        ttk.Button(
            list_buttons, text="Delete", style="Danger.TButton", command=self._delete_message
        ).grid(row=0, column=1, sticky="ew", padx=(3, 0))
        ttk.Button(
            list_buttons, text="▲", width=3, style="Subtle.TButton", command=lambda: self._move(-1)
        ).grid(row=1, column=0, sticky="ew", padx=(0, 3), pady=(4, 0))
        ttk.Button(
            list_buttons, text="▼", width=3, style="Subtle.TButton", command=lambda: self._move(1)
        ).grid(row=1, column=1, sticky="ew", padx=(3, 0), pady=(4, 0))
        self._toggle_enabled_btn = ttk.Button(
            list_buttons, text="Disable", command=self._toggle_message_enabled, state="disabled"
        )
        self._toggle_enabled_btn.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        ttk.Button(self._messages_panel, text="Load from disk…", command=self._load_from_disk).pack(
            fill=tk.X, pady=(6, 0)
        )

        # -- Structure tree panel ---------------------------------------------
        self._structure_panel = ttk.Frame(left)

        struct_bar = ttk.Frame(self._structure_panel)
        struct_bar.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(struct_bar, text="STRUCTURE", style="Section.TLabel").pack(side=tk.LEFT)
        ttk.Button(
            struct_bar, text="Collapse", style="Subtle.TButton", command=self.collapse_all_structure
        ).pack(side=tk.RIGHT, padx=(2, 0))
        ttk.Button(
            struct_bar, text="Expand", style="Subtle.TButton", command=self.expand_all_structure
        ).pack(side=tk.RIGHT)

        filter_row = ttk.Frame(self._structure_panel)
        filter_row.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(filter_row, text="Filter", style="Muted.TLabel").pack(side=tk.LEFT, padx=(0, 6))
        self._tree_filter_var = tk.StringVar(value="")
        self._tree_filter_entry = ttk.Entry(filter_row, textvariable=self._tree_filter_var)
        self._tree_filter_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._tree_filter_entry.bind("<KeyRelease>", lambda _e: self._populate_structure_tree())
        ttk.Button(
            filter_row, text="×", width=2, style="Subtle.TButton", command=self._clear_tree_filter
        ).pack(side=tk.LEFT, padx=(4, 0))

        self._structure_status_var = tk.StringVar(value="")
        self._structure_status_label = ttk.Label(
            self._structure_panel,
            textvariable=self._structure_status_var,
            style="Muted.TLabel",
            wraplength=240,
        )

        tree_frame = ttk.Frame(self._structure_panel)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        self.structure_tree = ttk.Treeview(
            tree_frame,
            columns=("value",),
            show="tree headings",
            selectmode="browse",
        )
        self.structure_tree.heading("#0", text="Node", anchor="w")
        self.structure_tree.heading("value", text="Value (dbl-click to edit)", anchor="w")
        self.structure_tree.column("#0", width=155, minwidth=80, stretch=True)
        self.structure_tree.column("value", width=125, minwidth=60, stretch=True)

        tree_v_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.structure_tree.yview)
        tree_h_scroll = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.structure_tree.xview)
        self.structure_tree.configure(yscrollcommand=tree_v_scroll.set, xscrollcommand=tree_h_scroll.set)
        self.structure_tree.grid(row=0, column=0, sticky="nsew")
        tree_v_scroll.grid(row=0, column=1, sticky="ns")
        tree_h_scroll.grid(row=1, column=0, sticky="ew")
        self.structure_tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.structure_tree.bind("<Double-1>", self._begin_inline_tree_edit)

        # -- Editor (right pane) ----------------------------------------------
        right = ttk.Frame(self._paned)
        self._paned.add(right, weight=1)
        right_inner = ttk.Frame(right)
        right_inner.pack(fill=tk.BOTH, expand=True, padx=(6, 8), pady=(6, 4))

        toolbar = ttk.Frame(right_inner)
        toolbar.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(toolbar, text="Name", style="Muted.TLabel").pack(side=tk.LEFT)
        self._name_var = tk.StringVar()
        name_entry = ttk.Entry(toolbar, textvariable=self._name_var, width=22)
        name_entry.pack(side=tk.LEFT, padx=(6, 12))
        name_entry.bind("<KeyRelease>", self._handle_name_change)

        ttk.Label(toolbar, text="Format", style="Muted.TLabel").pack(side=tk.LEFT)
        self._format_var = tk.StringVar(value="hl7")
        format_menu = ttk.OptionMenu(
            toolbar, self._format_var, "hl7", *_FORMATS, command=self._handle_format_change  # type: ignore[arg-type]
        )
        format_menu.pack(side=tk.LEFT, padx=(6, 8))

        ttk.Button(toolbar, text="Pretty Print", command=self._format_message).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(toolbar, text="Scrub PII", command=self.scrub_pii).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(toolbar, text="Find", style="Subtle.TButton", command=self.toggle_find_bar).pack(side=tk.RIGHT)

        iter_row = ttk.Frame(right_inner)
        iter_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Button(iter_row, text="+ Mark Field", command=self._mark_iteration_field).pack(side=tk.LEFT)
        self._edit_iter_btn = ttk.Button(
            iter_row, text="Edit Field…", command=self._edit_iteration_field, state="disabled"
        )
        self._edit_iter_btn.pack(side=tk.LEFT, padx=(6, 0))
        self._manage_iter_btn = ttk.Button(
            iter_row, text="Manage All…", command=self._manage_iteration_fields, state="disabled"
        )
        self._manage_iter_btn.pack(side=tk.LEFT, padx=(6, 0))
        self._clear_iter_btn = ttk.Button(
            iter_row, text="Clear All", style="Danger.TButton", command=self.clear_all_iterations, state="disabled"
        )
        self._clear_iter_btn.pack(side=tk.LEFT, padx=(6, 0))
        self._preview_iter_btn = ttk.Button(
            iter_row, text="Preview Sends…", command=self.preview_iterations, state="disabled"
        )
        self._preview_iter_btn.pack(side=tk.LEFT, padx=(6, 0))
        self._iteration_status_var = tk.StringVar(
            value="Highlight text (or select a tree node) → + Mark Field to vary values on Repeat > 1"
        )
        ttk.Label(iter_row, textvariable=self._iteration_status_var, style="Muted.TLabel").pack(
            side=tk.LEFT, padx=(10, 0)
        )

        # Collapsible Find & Replace bar (hidden until Cmd/Ctrl+F or Find button).
        self._find_bar = ttk.Frame(right_inner)
        self._find_var = tk.StringVar(value="")
        self._replace_var = tk.StringVar(value="")
        self._find_case_var = tk.BooleanVar(value=False)
        self._find_count_var = tk.StringVar(value="")

        ttk.Label(self._find_bar, text="Find", style="Muted.TLabel").pack(side=tk.LEFT)
        self._find_entry = ttk.Entry(self._find_bar, textvariable=self._find_var, width=18)
        self._find_entry.pack(side=tk.LEFT, padx=(4, 6))
        self._find_entry.bind("<KeyRelease>", lambda _e: self._run_find())
        self._find_entry.bind("<Return>", lambda _e: self.find_next())
        self._find_entry.bind("<Escape>", lambda _e: self.hide_find_bar())

        ttk.Label(self._find_bar, text="Replace", style="Muted.TLabel").pack(side=tk.LEFT)
        self._replace_entry = ttk.Entry(self._find_bar, textvariable=self._replace_var, width=16)
        self._replace_entry.pack(side=tk.LEFT, padx=(4, 6))
        self._replace_entry.bind("<Escape>", lambda _e: self.hide_find_bar())

        ttk.Checkbutton(
            self._find_bar, text="Aa", variable=self._find_case_var, command=self._run_find
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(self._find_bar, text="▲", width=2, style="Subtle.TButton", command=self.find_prev).pack(side=tk.LEFT)
        ttk.Button(self._find_bar, text="▼", width=2, style="Subtle.TButton", command=self.find_next).pack(
            side=tk.LEFT, padx=(2, 6)
        )
        ttk.Button(self._find_bar, text="Replace", command=self.replace_current).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(self._find_bar, text="All", command=self.replace_all).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Label(self._find_bar, textvariable=self._find_count_var, style="Muted.TLabel").pack(side=tk.LEFT)
        ttk.Button(self._find_bar, text="×", width=2, style="Subtle.TButton", command=self.hide_find_bar).pack(
            side=tk.RIGHT
        )

        self._text_frame = ttk.Frame(right_inner)
        self._text_frame.pack(fill=tk.BOTH, expand=True)
        self._text_frame.rowconfigure(0, weight=1)
        self._text_frame.columnconfigure(0, weight=1)

        self.text = tk.Text(
            self._text_frame,
            wrap="none",
            undo=True,
            exportselection=False,
            font=("Menlo", 11),
            bd=0,
            padx=10,
            pady=10,
            highlightthickness=1,
        )
        v_scroll = ttk.Scrollbar(self._text_frame, orient=tk.VERTICAL, command=self.text.yview)
        h_scroll = ttk.Scrollbar(self._text_frame, orient=tk.HORIZONTAL, command=self.text.xview)
        self.text.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        h_scroll.grid(row=1, column=0, sticky="ew")

        # Live path & cursor status bar at bottom of editor.
        status_bar = ttk.Frame(right_inner)
        status_bar.pack(fill=tk.X, pady=(4, 0))
        self._path_status_var = tk.StringVar(value="")
        self._path_label = ttk.Label(
            status_bar, textvariable=self._path_status_var, style="Muted.TLabel", cursor="hand2"
        )
        self._path_label.pack(side=tk.LEFT)
        self._path_label.bind("<Button-1>", self._copy_current_path)
        self._cursor_status_var = tk.StringVar(value="")
        ttk.Label(status_bar, textvariable=self._cursor_status_var, style="Muted.TLabel").pack(side=tk.RIGHT)

        configure_tags(self.text, self._theme)
        self.text.tag_configure(
            _STRUCTURE_SYNC_TAG, background=self._theme.select_bg, foreground=self._theme.select_fg
        )
        self._configure_find_tags(self._theme)
        self.text.bind("<<Modified>>", self._handle_text_modified)
        self.text.bind("<ButtonRelease-1>", self._on_editor_cursor_move)
        self.text.bind("<KeyRelease>", self._on_editor_cursor_move)

        self._set_editor_enabled(False)
        self.after_idle(self._init_sash)

    def _init_sash(self) -> None:
        if self._paned.winfo_ismapped():
            self._paned.sashpos(0, _LEFT_PANE_WIDTH)

    def _configure_find_tags(self, theme: Theme) -> None:
        if is_dark_theme(theme):
            self.text.tag_configure(_FIND_MATCH_TAG, background="#4A3A15", foreground="#FFFFFF")
            self.text.tag_configure(_FIND_CURRENT_TAG, background="#F8CA4D", foreground="#1B294A")
        else:
            self.text.tag_configure(_FIND_MATCH_TAG, background="#FEF3C7", foreground="#1B294A")
            self.text.tag_configure(_FIND_CURRENT_TAG, background="#F59E0B", foreground="#FFFFFF")

    def apply_theme(self, theme: Theme) -> None:
        """Re-colour syntax highlighting tags and surfaces for the given theme."""
        self._theme = theme
        border = get_border_color(theme)
        colors = get_semantic_colors(theme)
        configure_tags(self.text, theme)
        for idx in range(self._iter_tag_count):
            self.text.tag_configure(
                f"{_ITERATE_TAG_PREFIX}{idx}", background=colors["iterate_bg"], foreground=colors["iterate_fg"]
            )
        self.text.tag_configure(_STRUCTURE_SYNC_TAG, background=theme.select_bg, foreground=theme.select_fg)
        self._configure_find_tags(theme)
        self.text.configure(
            bg=theme.pane_bg,
            fg=theme.pane_fg,
            insertbackground=theme.pane_fg,
            selectbackground=theme.select_bg,
            selectforeground=theme.select_fg,
            highlightbackground=border,
            highlightcolor=theme.accent,
        )
        self.listbox.configure(
            bg=theme.pane_bg,
            fg=theme.pane_fg,
            selectbackground=theme.select_bg,
            selectforeground=theme.select_fg,
            highlightbackground=border,
            highlightcolor=theme.accent,
        )

    def apply_preferences(self, prefs: AppPreferences) -> None:
        """Apply font family/size, word wrap, and structure expansion preferences."""
        self._auto_expand_structure = prefs.auto_expand_structure
        self.text.configure(
            font=(prefs.editor_font_family, prefs.editor_font_size),
            wrap="word" if prefs.editor_word_wrap else "none",
        )
        self.listbox.configure(font=(prefs.ui_font_family, prefs.ui_font_size))
        if self._tree_nodes:
            self._populate_structure_tree()

    # -- left panel view switcher & structure tree ---------------------------

    def set_left_view(self, mode: LeftViewMode) -> None:
        """Switch the left panel between the Messages list and the Structure tree."""
        if mode == self._left_view:
            return
        self._cancel_inline_tree_edit()
        self._left_view = mode
        if mode == "structure":
            self._messages_panel.pack_forget()
            self._structure_panel.pack(fill=tk.BOTH, expand=True, padx=(8, 4), pady=(0, 4))
            self._messages_mode_btn.configure(style="TButton")
            self._structure_mode_btn.configure(style="Accent.TButton")
            self._rebuild_structure_tree()
            self._sync_tree_from_editor()
        else:
            self._structure_panel.pack_forget()
            self._messages_panel.pack(fill=tk.BOTH, expand=True, padx=(8, 4), pady=(0, 4))
            self._messages_mode_btn.configure(style="Accent.TButton")
            self._structure_mode_btn.configure(style="TButton")
            self.text.tag_remove(_STRUCTURE_SYNC_TAG, "1.0", tk.END)

    def toggle_left_view(self) -> None:
        self.set_left_view("structure" if self._left_view == "messages" else "messages")

    def expand_all_structure(self) -> None:
        self._set_all_tree_open(True)

    def collapse_all_structure(self) -> None:
        self._set_all_tree_open(False)

    def _clear_tree_filter(self) -> None:
        self._tree_filter_var.set("")
        self._populate_structure_tree()

    def _set_all_tree_open(self, is_open: bool, parent: str = "") -> None:
        for item_id in self.structure_tree.get_children(parent):
            self.structure_tree.item(item_id, open=is_open)
            self._set_all_tree_open(is_open, item_id)

    def _rebuild_structure_tree(self) -> None:
        self._cancel_inline_tree_edit()
        self._tree_nodes = []

        if self._selected_index is None:
            self.structure_tree.delete(*self.structure_tree.get_children())
            self._tree_nodes_by_item = {}
            self._span_to_item = {}
            self._set_structure_status("Select a message to inspect its structure.")
            self._update_status_bar()
            return

        message = self._messages[self._selected_index]
        content = self.text.get("1.0", "end-1c")
        nodes, error = parse_structure(content, message.format)
        if error:
            self.structure_tree.delete(*self.structure_tree.get_children())
            self._tree_nodes_by_item = {}
            self._span_to_item = {}
            self._set_structure_status(error)
            self._update_status_bar()
            return
        if not nodes:
            self.structure_tree.delete(*self.structure_tree.get_children())
            self._tree_nodes_by_item = {}
            self._span_to_item = {}
            self._set_structure_status("Message is empty.")
            self._update_status_bar()
            return

        self._tree_nodes = nodes
        self._populate_structure_tree()
        self._update_status_bar()

    def _populate_structure_tree(self) -> None:
        self._cancel_inline_tree_edit()
        self.structure_tree.delete(*self.structure_tree.get_children())
        self._tree_nodes_by_item = {}
        self._span_to_item = {}

        if not self._tree_nodes:
            return

        query = self._tree_filter_var.get().strip()
        visible = filter_structure_nodes(self._tree_nodes, query) if query else self._tree_nodes
        if not visible:
            self._set_structure_status(f"No nodes match '{query}'.")
            return

        self._set_structure_status("")
        self._insert_structure_nodes(
            "", visible, depth=0, expand_all=bool(query) or self._auto_expand_structure
        )

    def _set_structure_status(self, text: str) -> None:
        self._structure_status_var.set(text)
        if text:
            if not self._structure_status_label.winfo_ismapped():
                self._structure_status_label.pack(fill=tk.X, pady=(0, 4))
        elif self._structure_status_label.winfo_ismapped():
            self._structure_status_label.pack_forget()

    def _insert_structure_nodes(
        self,
        parent: str,
        nodes: list[StructureNode] | tuple[StructureNode, ...],
        depth: int,
        *,
        expand_all: bool = False,
    ) -> None:
        for node in nodes:
            item_id = self.structure_tree.insert(
                parent,
                tk.END,
                text=node.display_label,
                values=(node.value,),
                open=(expand_all or depth == 0),
            )
            self._tree_nodes_by_item[item_id] = node
            self._span_to_item[(node.start, node.end)] = item_id
            if node.children:
                self._insert_structure_nodes(item_id, node.children, depth + 1, expand_all=expand_all)

    def _on_tree_select(self, _event: tk.Event) -> None:
        """Sync Tree selection -> Code editor selection & scroll."""
        if self._suspend_events or self._selected_index is None:
            return
        selection = self.structure_tree.selection()
        if not selection:
            return
        item_id = selection[0]
        if item_id == self._ignore_tree_select_item:
            self._ignore_tree_select_item = None
            return
        self._ignore_tree_select_item = None
        node = self._tree_nodes_by_item.get(item_id)
        if node is None:
            return
        start_idx = f"1.0+{node.start}c"
        end_idx = f"1.0+{node.end}c"

        self.text.tag_remove("sel", "1.0", tk.END)
        self.text.tag_remove(_STRUCTURE_SYNC_TAG, "1.0", tk.END)
        if node.end > node.start:
            self.text.tag_add("sel", start_idx, end_idx)
            self.text.tag_add(_STRUCTURE_SYNC_TAG, start_idx, end_idx)
        self.text.mark_set(tk.INSERT, start_idx)
        self.text.see(start_idx)
        self._update_status_bar(node)

    def _begin_inline_tree_edit(self, event: tk.Event) -> None:
        """Double-clicking an editable leaf node opens an inline entry over its value cell."""
        item_id = self.structure_tree.identify_row(event.y)
        if not item_id:
            return
        node = self._tree_nodes_by_item.get(item_id)
        if node is None or not node.editable:
            return
        bbox = self.structure_tree.bbox(item_id, "value")
        if not bbox:
            return
        self._cancel_inline_tree_edit()
        x, y, width, height = bbox
        if node.value_start is None or node.value_end is None:
            return
        raw_val = self.text.get(f"1.0+{node.value_start}c", f"1.0+{node.value_end}c")
        entry_var = tk.StringVar(value=raw_val)
        entry = ttk.Entry(self.structure_tree, textvariable=entry_var)
        entry.place(x=x, y=y, width=max(width, 80), height=height)
        entry.focus_set()
        entry.select_range(0, tk.END)
        self._inline_editor = entry

        def _commit(_ev: tk.Event | None = None) -> None:
            new_val = entry_var.get()
            self._cancel_inline_tree_edit()
            self.apply_inline_edit(item_id, new_val)

        entry.bind("<Return>", _commit)
        entry.bind("<Escape>", lambda _ev: self._cancel_inline_tree_edit())
        entry.bind("<FocusOut>", lambda _ev: self._cancel_inline_tree_edit())

    def _cancel_inline_tree_edit(self) -> None:
        if self._inline_editor is not None:
            self._inline_editor.destroy()
            self._inline_editor = None

    def apply_inline_edit(self, item_id: str, new_value: str) -> bool:
        """Replace the editable value span of *item_id* in the editor and rebuild the tree."""
        if self._selected_index is None or self._is_iter_dialog_open():
            return False
        node = self._tree_nodes_by_item.get(item_id)
        if node is None or node.value_start is None or node.value_end is None:
            return False
        start_idx = f"1.0+{node.value_start}c"
        end_idx = f"1.0+{node.value_end}c"
        self._suspend_events = True
        try:
            self.text.delete(start_idx, end_idx)
            self.text.insert(start_idx, new_value)
            self.text.edit_modified(False)
            message = self._messages[self._selected_index]
            message.content = self.text.get("1.0", "end-1c")
            highlight(self.text, message.format)
            self._apply_iteration_tags(message)
        finally:
            self._suspend_events = False
        self._rebuild_structure_tree()
        self.text.mark_set(tk.INSERT, start_idx)
        self._sync_tree_from_editor()
        self._on_change()
        return True

    def _on_editor_cursor_move(self, _event: tk.Event | None = None) -> None:
        self._sync_tree_from_editor()
        self._update_status_bar()

    def _sync_tree_from_editor(self, _event: tk.Event | None = None) -> None:
        """Sync Code editor cursor/selection -> Structure tree node."""
        if self._suspend_events or self._selected_index is None:
            return
        self.text.tag_remove(_STRUCTURE_SYNC_TAG, "1.0", tk.END)
        if not self._tree_nodes:
            return

        sel_ranges = self.text.tag_ranges("sel")
        index_ref: object = sel_ranges[0] if sel_ranges else tk.INSERT
        offset = self._char_offset(index_ref)

        node = find_deepest_node(self._tree_nodes, offset)
        if node is None:
            return
        item_id = self._span_to_item.get((node.start, node.end))
        if item_id is None:
            return

        parent = self.structure_tree.parent(item_id)
        while parent:
            self.structure_tree.item(parent, open=True)
            parent = self.structure_tree.parent(parent)

        if self.structure_tree.selection() != (item_id,):
            self._ignore_tree_select_item = item_id
            self.structure_tree.selection_set(item_id)
        self.structure_tree.see(item_id)

    # -- status bar ---------------------------------------------------------

    def _update_status_bar(self, node: StructureNode | None = None) -> None:
        if self._selected_index is None:
            self._current_path = ""
            self._path_status_var.set("")
            self._cursor_status_var.set("")
            return
        index_str = self.text.index(tk.INSERT)
        line_str, col_str = index_str.split(".")
        content = self.text.get("1.0", "end-1c")
        byte_len = len(content.encode("utf-8"))
        self._cursor_status_var.set(f"Ln {line_str}, Col {int(col_str) + 1}  ·  {byte_len:,} bytes")

        if node is None and self._tree_nodes:
            offset = self._char_offset(tk.INSERT)
            node = find_deepest_node(self._tree_nodes, offset)

        if node is not None and node.path:
            self._current_path = node.path
            label = f"{node.path} · {node.description}" if node.description else node.path
            self._path_status_var.set(f"{label}  (click to copy)")
        else:
            self._current_path = ""
            self._path_status_var.set("")

    def _copy_current_path(self, _event: tk.Event) -> None:
        if not self._current_path:
            return
        self.clipboard_clear()
        self.clipboard_append(self._current_path)
        self._path_status_var.set(f"Copied: {self._current_path}")

    # -- find & replace -----------------------------------------------------

    def show_find_bar(self) -> None:
        if not self._find_bar.winfo_ismapped():
            self._find_bar.pack(fill=tk.X, pady=(0, 6), before=self._text_frame)
        ranges = self.text.tag_ranges("sel")
        if ranges:
            sel_text = self.text.get(ranges[0], ranges[1])
            if sel_text and "\n" not in sel_text:
                self._find_var.set(sel_text)
        self._find_entry.focus_set()
        self._find_entry.select_range(0, tk.END)
        self._run_find()

    def hide_find_bar(self) -> None:
        if self._find_bar.winfo_ismapped():
            self._find_bar.pack_forget()
        self.text.tag_remove(_FIND_MATCH_TAG, "1.0", tk.END)
        self.text.tag_remove(_FIND_CURRENT_TAG, "1.0", tk.END)
        self._find_matches = []
        self._find_index = -1
        self._find_count_var.set("")

    def toggle_find_bar(self) -> None:
        if self._find_bar.winfo_ismapped():
            self.hide_find_bar()
        else:
            self.show_find_bar()

    def _run_find(self) -> None:
        self.text.tag_remove(_FIND_MATCH_TAG, "1.0", tk.END)
        self.text.tag_remove(_FIND_CURRENT_TAG, "1.0", tk.END)
        self._find_matches = []
        self._find_index = -1

        query = self._find_var.get()
        if not query or self._selected_index is None:
            self._find_count_var.set("")
            return

        content = self.text.get("1.0", "end-1c")
        haystack = content if self._find_case_var.get() else content.lower()
        needle = query if self._find_case_var.get() else query.lower()

        pos = 0
        while True:
            idx = haystack.find(needle, pos)
            if idx == -1:
                break
            end = idx + len(query)
            self._find_matches.append((idx, end))
            self.text.tag_add(_FIND_MATCH_TAG, f"1.0+{idx}c", f"1.0+{end}c")
            pos = end

        if not self._find_matches:
            self._find_count_var.set("No matches")
            return
        self._find_index = 0
        self._highlight_current_match()

    def _highlight_current_match(self) -> None:
        self.text.tag_remove(_FIND_CURRENT_TAG, "1.0", tk.END)
        if not self._find_matches or not (0 <= self._find_index < len(self._find_matches)):
            return
        start, end = self._find_matches[self._find_index]
        start_idx, end_idx = f"1.0+{start}c", f"1.0+{end}c"
        self.text.tag_add(_FIND_CURRENT_TAG, start_idx, end_idx)
        self.text.mark_set(tk.INSERT, start_idx)
        self.text.see(start_idx)
        self._find_count_var.set(f"{self._find_index + 1}/{len(self._find_matches)}")

    def find_next(self) -> None:
        if not self._find_matches:
            self._run_find()
            return
        self._find_index = (self._find_index + 1) % len(self._find_matches)
        self._highlight_current_match()

    def find_prev(self) -> None:
        if not self._find_matches:
            self._run_find()
            return
        self._find_index = (self._find_index - 1) % len(self._find_matches)
        self._highlight_current_match()

    def replace_current(self) -> None:
        if self._selected_index is None or not self._find_matches or self._find_index < 0:
            return
        start, end = self._find_matches[self._find_index]
        replacement = self._replace_var.get()
        self.text.delete(f"1.0+{start}c", f"1.0+{end}c")
        self.text.insert(f"1.0+{start}c", replacement)
        self._commit_current_edits()
        highlight(self.text, self._messages[self._selected_index].format)
        self._rebuild_structure_tree()
        self._on_change()
        self._run_find()

    def replace_all(self) -> int:
        if self._selected_index is None or not self._find_matches:
            return 0
        replacement = self._replace_var.get()
        count = len(self._find_matches)
        self._suspend_events = True
        try:
            for start, end in reversed(self._find_matches):
                self.text.delete(f"1.0+{start}c", f"1.0+{end}c")
                self.text.insert(f"1.0+{start}c", replacement)
            self.text.edit_modified(False)
            message = self._messages[self._selected_index]
            message.content = self.text.get("1.0", "end-1c")
            highlight(self.text, message.format)
        finally:
            self._suspend_events = False
        self._rebuild_structure_tree()
        self._on_change()
        self._run_find()
        return count

    # -- PII scrubber & message import --------------------------------------

    def scrub_pii(self) -> None:
        """Anonymise clinical PII in the currently active message."""
        if self._selected_index is None:
            messagebox.showinfo("Ultra7", "Select a message first.")
            return
        self._commit_current_edits()
        message = self._messages[self._selected_index]
        scrubbed = anonymise_message(message.content, message.format)
        if scrubbed == message.content:
            messagebox.showinfo("Ultra7", "No clinical PII fields were found to scrub.")
            return
        message.content = scrubbed
        self._load_into_editor(self._selected_index)
        self._on_change()

    def add_message(self, message: Message) -> None:
        """Append *message* to the project list and select it."""
        self._commit_current_edits()
        self._messages.append(message)
        self._refresh_listbox(select=len(self._messages) - 1)
        self._on_change()

    def preview_iterations(self) -> None:
        """Open the Preview Next N Sends dialog for the active message."""
        if self._selected_index is None:
            messagebox.showinfo("Ultra7", "Select a message first.")
            return
        self._commit_current_edits()
        message = self._messages[self._selected_index]
        IterationPreviewDialog(self, message, count=5, theme=self._theme)

    # -- project wiring ----------------------------------------------------

    def _close_manage_dialog(self) -> None:
        if self._manage_iter_dialog is not None and self._manage_iter_dialog.winfo_exists():
            self._manage_iter_dialog.destroy()
        self._manage_iter_dialog = None

    def _is_iter_dialog_open(self) -> bool:
        if self._iter_dialog is not None and self._iter_dialog.winfo_exists():
            self._iter_dialog.lift()
            self._iter_dialog.focus_set()
            return True
        return False

    def set_messages(self, messages: list[Message]) -> None:
        self._close_manage_dialog()
        self._messages = list(messages)
        self._selected_index = None
        self._refresh_listbox()
        self._clear_editor()

    def get_messages(self) -> list[Message]:
        self._commit_current_edits()
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
        if self._is_iter_dialog_open():
            return
        self._commit_current_edits()
        message = Message(name=f"Message {len(self._messages) + 1}", format="hl7", content="")
        self._messages.append(message)
        self._refresh_listbox(select=len(self._messages) - 1)
        self._on_change()

    def _delete_message(self) -> None:
        if self._is_iter_dialog_open():
            return
        self._close_manage_dialog()
        indices = self.listbox.curselection()
        if not indices:
            if self._selected_index is None:
                return
            indices = (self._selected_index,)
        for index in reversed(indices):
            del self._messages[index]
        self._selected_index = None
        self._refresh_listbox()
        self._clear_editor()
        self._on_change()

    def _move(self, offset: int) -> None:
        if self._is_iter_dialog_open():
            return
        indices = self.listbox.curselection()
        if not indices:
            return
        new_indices = [i + offset for i in indices]
        if not all(0 <= ni < len(self._messages) for ni in new_indices):
            return
        selected = [self._messages[i] for i in indices]
        # Build the new list by sliding the selected block as a unit.
        result: list[Message] = []
        selected_set = set(indices)
        # For each position in the new list, decide whether it's a target
        # slot for a selected message or the next non-selected message.
        non_selected = (m for idx, m in enumerate(self._messages) if idx not in selected_set)
        ns: Message | None = next(non_selected, None)
        for ni in range(len(self._messages)):
            if ni in new_indices:
                # Find the selected message whose target is ni.
                for idx, msg in enumerate(selected):
                    if new_indices[idx] == ni:
                        result.append(msg)
                        break
            else:
                if ns is not None:
                    result.append(ns)
                ns = next(non_selected, None)
        self._messages[:] = result
        self._refresh_listbox(select=new_indices[-1])
        self._on_change()

    def _load_from_disk(self) -> None:
        if self._is_iter_dialog_open():
            return
        paths = filedialog.askopenfilenames(title="Load message(s)")
        if not paths:
            return
        errors: list[str] = []
        loaded_count = 0
        for path in paths:
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except OSError as exc:
                errors.append(f"{path}: {exc}")
                continue
            name = Path(path).name
            self._messages.append(Message(name=name, format=detect_format(content), content=content))
            loaded_count += 1

        if errors:
            messagebox.showerror("Ultra7", "Some files failed to load:\n" + "\n".join(errors))
        if loaded_count > 0:
            self._refresh_listbox(select=len(self._messages) - 1)
            self._on_change()

    # -- selection / editor sync --------------------------------------------

    def _handle_select(self, _event: tk.Event) -> None:
        if self._is_iter_dialog_open():
            if self._selected_index is not None:
                self.listbox.selection_clear(0, tk.END)
                self.listbox.selection_set(self._selected_index)
            return
        selection = self.listbox.curselection()
        if not selection:
            return
        active_index = self.listbox.index(tk.ACTIVE)
        if 0 <= active_index < len(self._messages):
            self._commit_current_edits()
            self._load_into_editor(active_index)
        self._update_toggle_enabled_button_for_selection()

    def _load_into_editor(self, index: int) -> None:
        self._close_manage_dialog()
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
        self._apply_iteration_tags(message)
        self._update_iteration_label(message)
        self._update_toggle_enabled_button_for_selection()
        self._rebuild_structure_tree()
        if self._find_bar.winfo_ismapped():
            self._run_find()
        self._suspend_events = False

    def _clear_editor(self) -> None:
        self._close_manage_dialog()
        self._suspend_events = True
        self._name_var.set("")
        self.text.delete("1.0", tk.END)
        self.text.edit_modified(False)
        self._set_editor_enabled(False)
        self._iteration_status_var.set(
            "Highlight text (or select a tree node) → + Mark Field to vary values on Repeat > 1"
        )
        self._edit_iter_btn.configure(state="disabled")
        self._manage_iter_btn.configure(state="disabled")
        self._clear_iter_btn.configure(state="disabled")
        self._preview_iter_btn.configure(state="disabled")
        self._toggle_enabled_btn.configure(text="Disable", state="disabled")
        self._rebuild_structure_tree()
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
        specs = message.all_iterations()
        if specs:
            surviving: list[IterationSpec] = []
            for idx, spec in enumerate(specs):
                ranges = self.text.tag_ranges(f"{_ITERATE_TAG_PREFIX}{idx}")
                if ranges:
                    spec.start = self._char_offset(ranges[0])
                    spec.end = self._char_offset(ranges[1])
                    if spec.end > spec.start:
                        surviving.append(spec)
            message.set_iterations(surviving)
            if len(surviving) != len(specs):
                self._apply_iteration_tags(message)
            self._update_iteration_label(message)

    # -- field change handlers ----------------------------------------------

    def _handle_name_change(self, _event: tk.Event) -> None:
        if self._selected_index is None or self._suspend_events:
            return
        index = self._selected_index
        msg = self._messages[index]
        msg.name = self._name_var.get()
        selection = self.listbox.curselection()
        prefix = "" if msg.enabled else "[off] "
        self.listbox.delete(index)
        self.listbox.insert(index, f"{prefix}{msg.name}")
        if not msg.enabled:
            self.listbox.itemconfig(index, foreground=_DISABLED_FG)
        for i in selection:
            self.listbox.selection_set(i)
        self._on_change()

    def _handle_format_change(self, value: str) -> None:
        if self._selected_index is None:
            return
        self._messages[self._selected_index].format = value  # type: ignore[assignment]
        highlight(self.text, value)  # type: ignore[arg-type]
        self._rebuild_structure_tree()
        self._sync_tree_from_editor()
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

        # Reformatting shifts character positions — try to relocate each marked
        # substring by its text; clear any that can't be found unambiguously.
        specs = message.all_iterations()
        if specs:
            relocated: list[IterationSpec] = []
            dropped = 0
            for spec in specs:
                marked_text = message.content[spec.start : spec.end]
                new_start = formatted.find(marked_text) if marked_text else -1
                if new_start >= 0 and formatted.count(marked_text) == 1:
                    spec.start = new_start
                    spec.end = new_start + len(marked_text)
                    relocated.append(spec)
                else:
                    dropped += 1
            message.set_iterations(relocated)
            if dropped:
                messagebox.showinfo(
                    "Ultra7",
                    f"Formatting cleared {dropped} iteration field(s) — marked text could not be relocated.",
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
        self._rebuild_structure_tree()
        self._sync_tree_from_editor()
        self._on_change()

    # -- iteration fields (multi-field supported) -----------------------------

    def _mark_iteration_field(self) -> None:
        """Mark the current text selection (or selected Structure tree leaf) as an iteration field."""
        if self._selected_index is None or self._is_iter_dialog_open():
            return
        start_off: int
        end_off: int
        sel_ranges = self.text.tag_ranges("sel")
        sync_ranges = self.text.tag_ranges(_STRUCTURE_SYNC_TAG)
        is_tree_sync_sel = (
            bool(sel_ranges)
            and bool(sync_ranges)
            and str(sel_ranges[0]) == str(sync_ranges[0])
            and str(sel_ranges[1]) == str(sync_ranges[1])
        )
        if sel_ranges and not is_tree_sync_sel:
            start_off = self._char_offset(sel_ranges[0])
            end_off = self._char_offset(sel_ranges[1])
        else:
            # Tree-generated selection (or no editor selection): use the selected leaf node's value span
            # so XML tags and JSON keys are never overwritten by iteration values.
            tree_sel = self.structure_tree.selection()
            node = self._tree_nodes_by_item.get(tree_sel[0]) if tree_sel else None
            if node is not None and node.value_start is not None and node.value_end is not None:
                start_off, end_off = node.value_start, node.value_end
            else:
                messagebox.showinfo(
                    "Ultra7",
                    "Highlight the part of the message you want to vary on each repeat "
                    "(e.g. MSH-10 control ID or NHS number), or select a leaf value in the Structure tree first.",
                )
                return
        if start_off >= end_off:
            return

        message = self._messages[self._selected_index]
        selected_text = self.text.get(f"1.0+{start_off}c", f"1.0+{end_off}c")
        existing = next(
            (s for s in message.all_iterations() if s.start == start_off and s.end == end_off),
            None,
        )
        self._run_iteration_dialog(message, start_off, end_off, selected_text, existing)

    def _edit_iteration_field(self) -> None:
        """Edit (or remove) the iteration field at cursor, or open Manage if multiple exist."""
        if self._selected_index is None or self._is_iter_dialog_open():
            return
        message = self._messages[self._selected_index]
        specs = message.all_iterations()
        if not specs:
            messagebox.showinfo("Ultra7", "No iteration field set for this message.")
            return
        cursor = self._char_offset(tk.INSERT)
        at_cursor = next((s for s in specs if s.start <= cursor <= s.end), None)
        if at_cursor is None and len(specs) > 1:
            self._manage_iteration_fields()
            return
        target = at_cursor or specs[0]
        selected_text = self.text.get(f"1.0+{target.start}c", f"1.0+{target.end}c")
        self._run_iteration_dialog(message, target.start, target.end, selected_text, target)

    def _manage_iteration_fields(self) -> None:
        """Open a table dialog listing all iteration fields on the active message."""
        if self._selected_index is None or self._is_iter_dialog_open():
            return
        self._commit_current_edits()
        target_message = self._messages[self._selected_index]
        specs = target_message.all_iterations()
        if not specs:
            messagebox.showinfo("Ultra7", "No iteration fields set for this message.")
            return

        self._close_manage_dialog()

        def _is_still_active() -> bool:
            if self._selected_index is None or self._messages[self._selected_index] is not target_message:
                self._close_manage_dialog()
                return False
            return True

        def _edit(spec: IterationSpec) -> None:
            if not _is_still_active():
                return
            snippet = self.text.get(f"1.0+{spec.start}c", f"1.0+{spec.end}c")
            self._run_iteration_dialog(target_message, spec.start, spec.end, snippet, spec)

        def _jump(spec: IterationSpec) -> None:
            if not _is_still_active():
                return
            start_idx = f"1.0+{spec.start}c"
            end_idx = f"1.0+{spec.end}c"
            self.text.tag_remove("sel", "1.0", tk.END)
            self.text.tag_add("sel", start_idx, end_idx)
            self.text.mark_set(tk.INSERT, start_idx)
            self.text.see(start_idx)
            self.text.focus_set()

        def _remove(spec: IterationSpec) -> None:
            if not _is_still_active():
                return
            updated = [
                s for s in target_message.all_iterations() if not (s.start == spec.start and s.end == spec.end)
            ]
            target_message.set_iterations(updated)
            self._apply_iteration_tags(target_message)
            self._update_iteration_label(target_message)
            self._on_change()

        def _clear_all() -> None:
            if not _is_still_active():
                return
            target_message.set_iterations([])
            self._apply_iteration_tags(target_message)
            self._update_iteration_label(target_message)
            self._on_change()

        self._manage_iter_dialog = ManageIterationsDialog(
            self,
            target_message.content,
            specs,
            on_edit=_edit,
            on_jump=_jump,
            on_remove=_remove,
            on_clear_all=_clear_all,
            theme=self._theme,
        )

    def clear_all_iterations(self) -> None:
        """Remove every iteration field from the currently active message."""
        if self._selected_index is None or self._is_iter_dialog_open():
            return
        self._close_manage_dialog()
        message = self._messages[self._selected_index]
        if not message.all_iterations():
            return
        message.set_iterations([])
        self._apply_iteration_tags(message)
        self._update_iteration_label(message)
        self._on_change()

    def _run_iteration_dialog(
        self, message: Message, start_off: int, end_off: int, selected_text: str, existing: IterationSpec | None
    ) -> None:
        if self._is_iter_dialog_open():
            return
        self._close_manage_dialog()
        original_content = self.text.get("1.0", "end-1c")
        dialog = IterationDialog(self, start_off, end_off, selected_text, existing, theme=self._theme)
        self._iter_dialog = dialog
        self._set_editor_enabled(False)
        try:
            self.wait_window(dialog)
        finally:
            self._iter_dialog = None
            if self._selected_index is not None:
                self._set_editor_enabled(True)

        # Ensure neither the active message nor its text changed while the dialog was open.
        if (
            self._selected_index is None
            or self._messages[self._selected_index] is not message
            or self.text.get("1.0", "end-1c") != original_content
        ):
            return

        current = message.all_iterations()
        if dialog.removed:
            updated = [s for s in current if not (s.start == start_off and s.end == end_off)]
            message.set_iterations(updated)
        elif dialog.result is not None:
            # Replace any overlapping spec, keep all non-overlapping specs.
            updated = [s for s in current if s.end <= start_off or s.start >= end_off]
            updated.append(dialog.result)
            message.set_iterations(updated)
        else:
            return
        self._apply_iteration_tags(message)
        self._update_iteration_label(message)
        self._on_change()

    def _apply_iteration_tags(self, message: Message) -> None:
        for idx in range(self._iter_tag_count):
            self.text.tag_remove(f"{_ITERATE_TAG_PREFIX}{idx}", "1.0", tk.END)
        specs = message.all_iterations()
        colors = get_semantic_colors(self._theme)
        for idx, spec in enumerate(specs):
            tag = f"{_ITERATE_TAG_PREFIX}{idx}"
            self.text.tag_configure(tag, background=colors["iterate_bg"], foreground=colors["iterate_fg"])
            self.text.tag_add(tag, f"1.0+{spec.start}c", f"1.0+{spec.end}c")
        self._iter_tag_count = max(self._iter_tag_count, len(specs))

    def _update_iteration_label(self, message: Message) -> None:
        specs = message.all_iterations()
        if not specs:
            self._iteration_status_var.set(
                "Highlight text (or select a tree node) → + Mark Field to vary values on Repeat > 1"
            )
            self._edit_iter_btn.configure(state="disabled")
            self._manage_iter_btn.configure(state="disabled")
            self._clear_iter_btn.configure(state="disabled")
            self._preview_iter_btn.configure(state="disabled")
            return
        self._edit_iter_btn.configure(state="normal")
        self._manage_iter_btn.configure(state="normal")
        self._clear_iter_btn.configure(state="normal")
        self._preview_iter_btn.configure(state="normal")
        if len(specs) > 1:
            modes = ", ".join(s.mode for s in specs)
            self._iteration_status_var.set(f"{len(specs)} fields ({modes}) — varies on Repeat > 1")
            return
        spec = specs[0]
        if spec.mode == "increment":
            self._iteration_status_var.set(f"Iterates: increment (step {spec.step}) — varies on Repeat > 1")
        elif spec.mode == "list":
            self._iteration_status_var.set(f"Iterates: list ({len(spec.values)} values) — varies on Repeat > 1")
        elif spec.mode == "nhs_number":
            self._iteration_status_var.set("Iterates: Mod-11 NHS Number — varies on Repeat > 1")
        else:
            self._iteration_status_var.set(f"Iterates: timestamp ({spec.timestamp_format}) — varies on Repeat > 1")
