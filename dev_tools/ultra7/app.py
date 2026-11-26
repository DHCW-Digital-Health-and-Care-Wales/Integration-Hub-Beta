"""Ultra7 entry point — window chrome, layout, and wiring between UI panels.

Run with:
    cd dev_tools/ultra7
    uv run python app.py
"""
from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from ultra7.export import extension_for, sanitize_filename, unique_filename
from ultra7.models import Endpoint, Message, Project
from ultra7.senders.base import SendResult
from ultra7.settings import (
    MAX_EDITOR_FONT_SIZE,
    MIN_EDITOR_FONT_SIZE,
    AppPreferences,
    load_preferences,
    save_preferences,
)
from ultra7.storage import ProjectStore
from ultra7.ui.diff_dialog import DiffDialog
from ultra7.ui.editor_pane import EditorPane
from ultra7.ui.endpoint_dialog import EndpointDialog
from ultra7.ui.help_dialog import AboutDialog, HelpDialog
from ultra7.ui.log_panel import LogPanel
from ultra7.ui.mock_receiver_dialog import MockReceiverDialog
from ultra7.ui.preferences_dialog import PreferencesDialog
from ultra7.ui.send_controls import SendControls
from ultra7.ui.sidebar import Sidebar
from ultra7.ui.themes import (
    THEMES,
    Theme,
    blend_colors,
    get_accent_fg,
    get_border_color,
    get_hover_bg,
    get_muted_fg,
    get_semantic_colors,
    get_theme,
)

# DHCW brand colours.
DHCW_NAVY = "#1B294A"
DHCW_BLUE = "#12A3C9"
DHCW_YELLOW = "#F8CA4D"
NHS_BLUE = "#325083"
BG = "#F5F7FA"

_SIDEBAR_EXPANDED_WIDTH = 240
_EDITOR_LOG_SASH_HEIGHT = 500


def _format_endpoint_summary(endpoint: Endpoint) -> str:
    if endpoint.kind == "mllp":
        if endpoint.host and endpoint.port:
            return f"MLLP · {endpoint.host}:{endpoint.port}"
        return "MLLP · not configured"
    if endpoint.url:
        return f"{endpoint.kind.upper()} · {endpoint.url}"
    return f"{endpoint.kind.upper()} · not configured"


class Ultra7App(tk.Tk):
    """Top-level Ultra7 window."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Ultra7 — Endpoint Tester")
        self.geometry("1200x800")
        self.configure(bg=BG)

        self.store = ProjectStore()
        self.current_project: Project | None = None
        self._dirty = False
        self._prefs: AppPreferences = load_preferences()
        self._theme: Theme = get_theme(self._prefs.theme)
        self._mock_receiver_win: MockReceiverDialog | None = None
        self._help_win: HelpDialog | None = None

        self._build_menu()
        self._build_layout()
        self._bind_shortcuts()
        self._refresh_sidebar()
        self._apply_preferences(self._prefs, save=False)
        if self._prefs.default_left_view == "structure":
            self.editor_pane.set_left_view("structure")

    # -- construction ----------------------------------------------------------

    def _build_menu(self) -> None:
        accel = "Cmd" if sys.platform == "darwin" else "Ctrl"
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="New Project", command=self._new_project)
        file_menu.add_command(label="Save Project", accelerator=f"{accel}+S", command=self._save_current_project)
        file_menu.add_separator()
        file_menu.add_command(label="Export Selected Message(s)…", command=self._export_selected_messages)
        file_menu.add_command(label="Export Messages…", command=self._export_messages)
        file_menu.add_separator()
        file_menu.add_command(label="Preferences…", accelerator=f"{accel}+,", command=self._open_preferences)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_exit)
        menubar.add_cascade(label="File", menu=file_menu)

        view_menu = tk.Menu(menubar, tearoff=False)
        view_menu.add_command(label="Toggle Sidebar", accelerator=f"{accel}+B", command=self._toggle_sidebar)
        view_menu.add_command(
            label="Toggle Structure View", accelerator=f"{accel}+T", command=self._toggle_structure_view
        )
        view_menu.add_command(label="Toggle Log Panel", accelerator=f"{accel}+L", command=self._toggle_log_panel)
        view_menu.add_separator()
        view_menu.add_command(
            label="Increase Editor Font", accelerator=f"{accel}++", command=lambda: self._adjust_editor_font(1)
        )
        view_menu.add_command(
            label="Decrease Editor Font", accelerator=f"{accel}+-", command=lambda: self._adjust_editor_font(-1)
        )
        view_menu.add_command(
            label="Reset Editor Font", accelerator=f"{accel}+0", command=self._reset_editor_font
        )
        menubar.add_cascade(label="View", menu=view_menu)

        tools_menu = tk.Menu(menubar, tearoff=False)
        tools_menu.add_command(label="Find / Replace…", accelerator=f"{accel}+F", command=self._open_find)
        tools_menu.add_command(label="Pretty Print", accelerator=f"{accel}+Shift+F", command=self._pretty_print)
        tools_menu.add_separator()
        tools_menu.add_command(label="Compare Messages…", command=self._compare_messages)
        tools_menu.add_command(label="Scrub PII (Anonymise)", command=self._scrub_pii)
        tools_menu.add_command(label="Preview Iteration Sends…", command=self._preview_iterations)
        tools_menu.add_separator()
        tools_menu.add_command(label="Mock Receiver…", command=self._open_mock_receiver)
        menubar.add_cascade(label="Tools", menu=tools_menu)

        self._theme_var = tk.StringVar(value=self._prefs.theme)
        theme_menu = tk.Menu(menubar, tearoff=False)
        for theme in THEMES:
            theme_menu.add_radiobutton(
                label=theme.name,
                value=theme.name,
                variable=self._theme_var,
                command=lambda name=theme.name: self._apply_theme(name),  # type: ignore[misc]
            )
        theme_menu.add_separator()
        theme_menu.add_command(label="Fonts & Preferences…", accelerator=f"{accel}+,", command=self._open_preferences)
        menubar.add_cascade(label="Theme", menu=theme_menu)

        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="Ultra7 Help Guide", accelerator="F1", command=lambda: self._open_help())
        help_menu.add_command(label="Keyboard Shortcuts", command=lambda: self._open_help("shortcuts"))
        help_menu.add_command(label="HL7 v2.x Quick Reference", command=lambda: self._open_help("hl7-reference"))
        help_menu.add_separator()
        help_menu.add_command(label="About Ultra7", command=self._open_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.configure(menu=menubar)
        self.protocol("WM_DELETE_WINDOW", self._on_exit)

    def _bind_shortcuts(self) -> None:
        mod = "Command" if sys.platform == "darwin" else "Control"
        self.bind_all(f"<{mod}-s>", lambda _e: self._save_current_project())
        self.bind_all(f"<{mod}-comma>", lambda _e: self._open_preferences())
        self.bind_all(f"<{mod}-f>", lambda _e: self._open_find())
        self.bind_all(f"<{mod}-Shift-F>", lambda _e: self._pretty_print())
        self.bind_all(f"<{mod}-b>", lambda _e: self._toggle_sidebar())
        self.bind_all(f"<{mod}-t>", lambda _e: self._toggle_structure_view())
        self.bind_all(f"<{mod}-l>", lambda _e: self._toggle_log_panel())
        self.bind_all(f"<{mod}-equal>", lambda _e: self._adjust_editor_font(1))
        self.bind_all(f"<{mod}-plus>", lambda _e: self._adjust_editor_font(1))
        self.bind_all(f"<{mod}-minus>", lambda _e: self._adjust_editor_font(-1))
        self.bind_all(f"<{mod}-0>", lambda _e: self._reset_editor_font())
        self.bind_all(f"<{mod}-Return>", lambda _e: self.send_controls._start_send_once())  # noqa: SLF001
        self.bind_all("<F1>", lambda _e: self._open_help())

    def _build_layout(self) -> None:
        main = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main.pack(fill=tk.BOTH, expand=True)
        self._main_pane = main
        self._sidebar_visible = True
        self._sidebar_expanded_width = _SIDEBAR_EXPANDED_WIDTH

        self.sidebar = Sidebar(
            main,
            on_select=self._select_project,
            on_new=self._new_project,
            on_remove=self._remove_project,
            on_run_selected=self._run_selected_projects,
        )
        main.add(self.sidebar, weight=0)

        right = ttk.Frame(main)
        main.add(right, weight=1)

        header = ttk.Frame(right)
        header.pack(fill=tk.X, padx=10, pady=(10, 8))
        ttk.Button(header, text="☰", width=3, style="Subtle.TButton", command=self._toggle_sidebar).pack(
            side=tk.LEFT, padx=(0, 10)
        )
        title_box = ttk.Frame(header)
        title_box.pack(side=tk.LEFT, fill=tk.Y)
        self._project_label_var = tk.StringVar(value="No project selected")
        self._project_title_label = ttk.Label(
            title_box, textvariable=self._project_label_var, font=("Rubik", 14, "bold")
        )
        self._project_title_label.pack(anchor="w")
        self._endpoint_summary_var = tk.StringVar(value="Select or create a project in the sidebar")
        ttk.Label(title_box, textvariable=self._endpoint_summary_var, style="Muted.TLabel").pack(anchor="w")

        ttk.Button(header, text="?", width=3, style="Subtle.TButton", command=self._open_help).pack(
            side=tk.RIGHT, padx=(6, 0)
        )
        ttk.Button(header, text="Save", style="Accent.TButton", command=self._save_current_project).pack(
            side=tk.RIGHT, padx=(6, 0)
        )
        ttk.Button(header, text="Configure Endpoint…", command=self._configure_endpoint).pack(side=tk.RIGHT)

        ttk.Separator(right, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=10, pady=(0, 2))

        body = ttk.PanedWindow(right, orient=tk.VERTICAL)
        body.pack(fill=tk.BOTH, expand=True)
        self._body_pane = body

        self.editor_pane = EditorPane(body, on_change=self._mark_dirty)
        body.add(self.editor_pane, weight=3)

        bottom = ttk.Frame(body)
        self.send_controls = SendControls(
            bottom,
            get_endpoint=self._require_endpoint,
            get_messages=self.editor_pane.get_messages,
            get_selected_messages=self.editor_pane.get_selected_messages,
            on_result=self._log_result,
            on_info=self._log_info,
            on_change=self._mark_dirty,
        )
        self.send_controls.pack(fill=tk.X, padx=4, pady=4)

        self.log_panel = LogPanel(bottom)
        self.log_panel.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))

        # The log panel is the second pane, resizable by dragging the sash above it.
        body.add(bottom, weight=1)

        self._set_project_controls_enabled(False)
        # Sash positions can only be set once the window has real geometry.
        self.after_idle(lambda: main.sashpos(0, _SIDEBAR_EXPANDED_WIDTH))
        self.after_idle(lambda: body.sashpos(0, _EDITOR_LOG_SASH_HEIGHT))

    def _toggle_sidebar(self) -> None:
        if self._sidebar_visible:
            self._sidebar_expanded_width = self._main_pane.sashpos(0)
            self._main_pane.forget(self.sidebar)
        else:
            self._main_pane.insert(0, self.sidebar, weight=0)
            self._main_pane.sashpos(0, self._sidebar_expanded_width)
        self._sidebar_visible = not self._sidebar_visible

    def _toggle_structure_view(self) -> None:
        self.editor_pane.toggle_left_view()

    def _apply_theme(self, name: str, *, save: bool = True) -> None:
        theme = get_theme(name)
        self._theme = theme
        self._prefs.theme = theme.name
        self._theme_var.set(theme.name)
        self.configure(bg=theme.bg)
        border_color = get_border_color(theme)
        muted_fg = get_muted_fg(theme)
        hover_bg = get_hover_bg(theme)
        accent_fg = get_accent_fg(theme)
        accent_hover = blend_colors(theme.accent, accent_fg, 0.14)
        disabled_bg = blend_colors(theme.pane_bg, theme.bg, 0.5)
        colors = get_semantic_colors(theme)

        ui_family = self._prefs.ui_font_family
        ui_size = self._prefs.ui_font_size
        small_size = max(8, ui_size - 1)
        section_size = max(7, ui_size - 2)
        self._project_title_label.configure(font=(ui_family, ui_size + 4, "bold"))

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background=theme.bg, foreground=theme.fg, font=(ui_family, ui_size))
        style.configure("TFrame", background=theme.bg)
        style.configure("TLabel", background=theme.bg, foreground=theme.fg, font=(ui_family, ui_size))
        style.configure("Muted.TLabel", background=theme.bg, foreground=muted_fg, font=(ui_family, small_size))
        style.configure(
            "Section.TLabel", background=theme.bg, foreground=muted_fg, font=(ui_family, section_size, "bold")
        )
        style.configure("TCheckbutton", background=theme.bg, foreground=theme.fg, font=(ui_family, small_size))
        style.map("TCheckbutton", background=[("active", theme.bg)])

        style.configure(
            "TButton",
            background=theme.pane_bg,
            foreground=theme.fg,
            bordercolor=border_color,
            lightcolor=theme.pane_bg,
            darkcolor=theme.pane_bg,
            focuscolor=theme.accent,
            borderwidth=1,
            relief="flat",
            padding=(10, 5),
            font=(ui_family, small_size),
        )
        style.map(
            "TButton",
            background=[("disabled", disabled_bg), ("pressed", hover_bg), ("active", hover_bg)],
            foreground=[("disabled", muted_fg)],
            bordercolor=[("focus", theme.accent), ("active", theme.accent)],
        )

        style.configure(
            "Accent.TButton",
            background=theme.accent,
            foreground=accent_fg,
            bordercolor=theme.accent,
            lightcolor=theme.accent,
            darkcolor=theme.accent,
            focuscolor=accent_fg,
            borderwidth=1,
            relief="flat",
            padding=(12, 5),
            font=(ui_family, small_size, "bold"),
        )
        style.map(
            "Accent.TButton",
            background=[("disabled", disabled_bg), ("pressed", accent_hover), ("active", accent_hover)],
            foreground=[("disabled", muted_fg), ("pressed", accent_fg), ("active", accent_fg)],
            bordercolor=[("disabled", border_color)],
        )

        style.configure(
            "Subtle.TButton",
            background=theme.bg,
            foreground=theme.fg,
            bordercolor=theme.bg,
            lightcolor=theme.bg,
            darkcolor=theme.bg,
            borderwidth=0,
            relief="flat",
            padding=(8, 4),
            font=(ui_family, small_size),
        )
        style.map(
            "Subtle.TButton",
            background=[("disabled", theme.bg), ("active", hover_bg), ("pressed", hover_bg)],
            foreground=[("disabled", muted_fg)],
        )

        style.configure(
            "Danger.TButton",
            background=theme.pane_bg,
            foreground=colors["danger"],
            bordercolor=border_color,
            lightcolor=theme.pane_bg,
            darkcolor=theme.pane_bg,
            borderwidth=1,
            relief="flat",
            padding=(10, 5),
            font=(ui_family, small_size),
        )
        style.map(
            "Danger.TButton",
            background=[("disabled", disabled_bg), ("active", colors["danger"]), ("pressed", colors["danger"])],
            foreground=[("disabled", muted_fg), ("active", "#FFFFFF"), ("pressed", "#FFFFFF")],
            bordercolor=[("active", colors["danger"])],
        )

        style.configure(
            "TEntry",
            fieldbackground=theme.pane_bg,
            foreground=theme.pane_fg,
            insertcolor=theme.pane_fg,
            bordercolor=border_color,
            lightcolor=theme.pane_bg,
            darkcolor=theme.pane_bg,
            padding=(8, 5),
            relief="flat",
            font=(ui_family, ui_size),
        )
        style.map(
            "TEntry",
            bordercolor=[("focus", theme.accent)],
            fieldbackground=[("disabled", disabled_bg)],
            foreground=[("disabled", muted_fg)],
        )

        style.configure(
            "TSpinbox",
            fieldbackground=theme.pane_bg,
            foreground=theme.pane_fg,
            background=theme.pane_bg,
            arrowcolor=muted_fg,
            bordercolor=border_color,
            padding=(6, 4),
            relief="flat",
            font=(ui_family, ui_size),
        )
        style.map("TSpinbox", bordercolor=[("focus", theme.accent)])

        style.configure(
            "TMenubutton",
            background=theme.pane_bg,
            foreground=theme.fg,
            bordercolor=border_color,
            arrowcolor=muted_fg,
            padding=(8, 5),
            relief="flat",
            font=(ui_family, small_size),
        )
        style.map("TMenubutton", background=[("active", hover_bg)], bordercolor=[("active", theme.accent)])

        style.configure("TPanedwindow", background=border_color, sashwidth=4, sashrelief="flat")
        style.configure(
            "TScrollbar",
            background=border_color,
            troughcolor=theme.pane_bg,
            bordercolor=theme.pane_bg,
            lightcolor=border_color,
            darkcolor=border_color,
            arrowcolor=muted_fg,
            arrowsize=0,
            relief="flat",
            borderwidth=0,
        )
        style.map("TScrollbar", background=[("active", muted_fg), ("pressed", theme.accent)])
        style.configure("Horizontal.TSeparator", background=border_color)
        style.configure("Vertical.TSeparator", background=border_color)
        style.configure(
            "Treeview",
            background=theme.pane_bg,
            foreground=theme.pane_fg,
            fieldbackground=theme.pane_bg,
            bordercolor=border_color,
            lightcolor=theme.pane_bg,
            darkcolor=theme.pane_bg,
            font=(ui_family, small_size),
            rowheight=self._prefs.tree_row_height,
        )
        style.map(
            "Treeview",
            background=[("selected", theme.select_bg)],
            foreground=[("selected", theme.select_fg)],
        )
        style.configure(
            "Treeview.Heading",
            background=theme.bg,
            foreground=muted_fg,
            bordercolor=border_color,
            lightcolor=theme.bg,
            darkcolor=theme.bg,
            font=(ui_family, section_size, "bold"),
            relief="flat",
        )

        self.editor_pane.apply_theme(theme)
        self.log_panel.apply_theme(theme)
        self.sidebar.apply_theme(theme)
        if save:
            save_preferences(self._prefs)

    def _apply_preferences(self, prefs: AppPreferences, *, save: bool = True) -> None:
        self._prefs = prefs
        self._apply_theme(prefs.theme, save=False)
        self.editor_pane.apply_preferences(prefs)
        self.log_panel.apply_preferences(prefs)
        self.sidebar.apply_preferences(prefs)
        if save:
            save_preferences(self._prefs)

    def _open_preferences(self) -> None:
        original = AppPreferences.from_dict(self._prefs.to_dict())
        dialog = PreferencesDialog(
            self,
            original,
            on_apply=lambda updated: self._apply_preferences(updated, save=True),
        )
        self.wait_window(dialog)
        if dialog.result is not None:
            self._apply_preferences(dialog.result, save=True)

    def _adjust_editor_font(self, delta: int) -> None:
        new_size = max(MIN_EDITOR_FONT_SIZE, min(MAX_EDITOR_FONT_SIZE, self._prefs.editor_font_size + delta))
        if new_size != self._prefs.editor_font_size:
            self._prefs.editor_font_size = new_size
            self._apply_preferences(self._prefs, save=True)

    def _reset_editor_font(self) -> None:
        default_size = AppPreferences().editor_font_size
        if self._prefs.editor_font_size != default_size:
            self._prefs.editor_font_size = default_size
            self._apply_preferences(self._prefs, save=True)

    # -- project lifecycle -------------------------------------------------------

    def _refresh_sidebar(self, select: str | None = None) -> None:
        names = self.store.list_projects()
        self.sidebar.set_projects(names, select=select)

    def _new_project(self) -> None:
        name = simpledialog.askstring("New Project", "Project name:", parent=self)
        if not name:
            return
        if self.store.exists(name):
            messagebox.showerror("Ultra7", f"A project named '{name}' already exists.")
            return
        project = Project(name=name)
        self.store.save(project)
        self._refresh_sidebar(select=name)
        self._load_project(project)

    def _select_project(self, name: str) -> None:
        if self.current_project and self.current_project.name == name:
            return
        self._save_if_dirty()
        try:
            project = self.store.load(name)
        except (OSError, ValueError, KeyError) as exc:
            messagebox.showerror("Ultra7", f"Could not load project '{name}': {exc}")
            return
        self._load_project(project)

    def _remove_project(self, name: str) -> None:
        if not messagebox.askyesno("Ultra7", f"Remove project '{name}'? This cannot be undone."):
            return
        self.store.delete(name)
        if self.current_project and self.current_project.name == name:
            self.current_project = None
            self._project_label_var.set("No project selected")
            self._endpoint_summary_var.set("Select or create a project in the sidebar")
            self.editor_pane.set_messages([])
            self._set_project_controls_enabled(False)
        self._refresh_sidebar()

    def _load_project(self, project: Project) -> None:
        self.current_project = project
        self._dirty = False
        self._project_label_var.set(project.name)
        self._endpoint_summary_var.set(_format_endpoint_summary(project.endpoint))
        self.editor_pane.set_messages(project.messages)
        self.send_controls.set_repeat_and_delay(project.repeat_count, project.delay_ms)
        self._set_project_controls_enabled(True)

    def _save_current_project(self) -> None:
        if self.current_project is None:
            return
        self.current_project.messages = self.editor_pane.get_messages()
        self.current_project.repeat_count = self.send_controls.get_repeat_count()
        self.current_project.delay_ms = self.send_controls.get_delay_ms()
        self.store.save(self.current_project)
        self._dirty = False

    def _save_if_dirty(self) -> None:
        if self._dirty and self.current_project is not None:
            self._save_current_project()

    def _mark_dirty(self) -> None:
        self._dirty = True

    def _export_selected_messages(self) -> None:
        messages = self.editor_pane.get_selected_messages()
        if not messages:
            messagebox.showinfo("Ultra7", "No message selected.")
            return
        if len(messages) == 1:
            self._export_single_message(messages[0])
        else:
            self._export_messages_to_folder(messages, title="Export selected messages to folder")

    def _export_messages(self) -> None:
        messages = self.editor_pane.get_messages()
        if not messages:
            messagebox.showinfo("Ultra7", "No messages to export.")
            return
        self._export_messages_to_folder(messages, title="Export messages to folder")

    def _export_single_message(self, message: Message) -> None:
        ext = extension_for(message.format)
        path = filedialog.asksaveasfilename(
            title="Export message",
            defaultextension=ext,
            initialfile=f"{sanitize_filename(message.name)}{ext}",
            filetypes=[(f"{message.format.upper()} files", f"*{ext}"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(message.content)
        except OSError as exc:
            messagebox.showerror("Ultra7", f"Could not export message: {exc}")

    def _export_messages_to_folder(self, messages: list[Message], title: str) -> None:
        directory = filedialog.askdirectory(title=title)
        if not directory:
            return

        used_names: set[str] = set()
        errors: list[str] = []
        for message in messages:
            filename = unique_filename(sanitize_filename(message.name), extension_for(message.format), used_names)
            try:
                with open(Path(directory) / filename, "w", encoding="utf-8") as f:
                    f.write(message.content)
            except OSError as exc:
                errors.append(f"{filename}: {exc}")

        if errors:
            messagebox.showerror("Ultra7", "Some messages failed to export:\n" + "\n".join(errors))
        else:
            messagebox.showinfo("Ultra7", f"Exported {len(messages)} message(s) to {directory}")

    def _require_endpoint(self) -> Endpoint:
        if self.current_project is None:
            return Endpoint()
        return self.current_project.endpoint

    def _configure_endpoint(self) -> None:
        if self.current_project is None:
            messagebox.showinfo("Ultra7", "Select or create a project first.")
            return
        dialog = EndpointDialog(self, self.current_project.endpoint, theme=self._theme)
        self.wait_window(dialog)
        if dialog.result is not None:
            self.current_project.endpoint = dialog.result
            self._endpoint_summary_var.set(_format_endpoint_summary(dialog.result))
            self._mark_dirty()
            self._save_current_project()

    def _run_selected_projects(self, selected_names: list[str]) -> None:
        """Run all selected projects in batch mode."""
        if not selected_names:
            messagebox.showinfo("Ultra7", "No projects selected. Check projects to run them.")
            return

        # Load selected projects
        if self.current_project is not None and self.current_project.name in selected_names:
            self._save_current_project()

        projects: list[Project] = []
        errors: list[str] = []
        for name in selected_names:
            try:
                project = self.store.load(name)
                projects.append(project)
            except (OSError, ValueError, KeyError) as exc:
                errors.append(f"{name}: {exc}")

        if errors:
            messagebox.showerror("Ultra7", "Some projects failed to load:\n" + "\n".join(errors))

        if not projects:
            return

        if not self.send_controls.start_batch(projects):
            messagebox.showinfo("Ultra7", "A send is already in progress.")

    def _set_project_controls_enabled(self, enabled: bool) -> None:
        self.send_controls.set_enabled(enabled)

    # -- logging / exit -------------------------------------------------------

    def _log_result(self, name: str, result: SendResult) -> None:
        self.log_panel.append(name, result)

    def _log_info(self, text: str) -> None:
        self.log_panel.append_info(text)

    def _toggle_log_panel(self) -> None:
        if self.log_panel.winfo_ismapped():
            self.log_panel.pack_forget()
        else:
            self.log_panel.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))

    def _open_find(self) -> None:
        self.editor_pane.show_find_bar()

    def _pretty_print(self) -> None:
        self.editor_pane._format_message()  # noqa: SLF001

    def _scrub_pii(self) -> None:
        self.editor_pane.scrub_pii()

    def _preview_iterations(self) -> None:
        self.editor_pane.preview_iterations()

    def _compare_messages(self) -> None:
        messages = self.editor_pane.get_messages()
        if len(messages) < 2:
            messagebox.showinfo("Ultra7", "Add at least two messages to compare.")
            return
        selected = self.editor_pane.listbox.curselection()
        left_idx = selected[0] if len(selected) >= 1 else 0
        right_idx = selected[1] if len(selected) >= 2 else (1 if left_idx == 0 else 0)
        DiffDialog(self, messages, initial_left=left_idx, initial_right=right_idx, theme=self._theme)

    def _open_mock_receiver(self) -> None:
        if self._mock_receiver_win is not None and self._mock_receiver_win.winfo_exists():
            self._mock_receiver_win.lift()
            return
        self._mock_receiver_win = MockReceiverDialog(
            self, on_import_message=self._import_received_message, theme=self._theme
        )

    def _import_received_message(self, message: Message) -> None:
        if self.current_project is None:
            messagebox.showinfo("Ultra7", "Select or create a project first to import messages.")
            return
        self.editor_pane.add_message(message)

    def _open_help(self, topic_id: str | None = None) -> None:
        if self._help_win is not None and self._help_win.winfo_exists():
            if topic_id is not None:
                self._help_win.select_topic(topic_id)
            self._help_win.lift()
            return
        self._help_win = HelpDialog(self, initial_topic_id=topic_id, theme=self._theme)

    def _open_about(self) -> None:
        AboutDialog(self, theme=self._theme)

    def _on_exit(self) -> None:
        if self._mock_receiver_win is not None and self._mock_receiver_win.winfo_exists():
            self._mock_receiver_win.stop_server()
        self._save_if_dirty()
        self.destroy()


def main() -> None:
    app = Ultra7App()
    app.lift()
    app.attributes("-topmost", True)
    app.after(100, lambda: app.attributes("-topmost", False))
    app.focus_force()
    app.mainloop()


if __name__ == "__main__":
    main()
