"""Ultra7 entry point — window chrome, layout, and wiring between UI panels.

Run with:
    cd dev_tools/ultra7
    uv run python app.py
"""
from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from ultra7.export import extension_for, sanitize_filename, unique_filename
from ultra7.iteration import apply_iteration
from ultra7.models import Endpoint, Message, Project
from ultra7.senders import get_sender
from ultra7.senders.base import SendResult
from ultra7.settings import load_theme_name, save_theme_name
from ultra7.storage import ProjectStore
from ultra7.ui.editor_pane import EditorPane
from ultra7.ui.endpoint_dialog import EndpointDialog
from ultra7.ui.log_panel import LogPanel
from ultra7.ui.send_controls import SendControls
from ultra7.ui.sidebar import Sidebar
from ultra7.ui.themes import THEMES, get_border_color, get_theme

# DHCW brand colours.
DHCW_NAVY = "#1B294A"
DHCW_BLUE = "#12A3C9"
DHCW_YELLOW = "#F8CA4D"
NHS_BLUE = "#325083"
BG = "#F5F7FA"

_SIDEBAR_EXPANDED_WIDTH = 220
_EDITOR_LOG_SASH_HEIGHT = 480


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

        self._build_menu()
        self._build_layout()
        self._refresh_sidebar()
        self._apply_theme(load_theme_name())

    # -- construction ----------------------------------------------------------

    def _build_menu(self) -> None:
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="New Project", command=self._new_project)
        file_menu.add_command(label="Save Project", command=self._save_current_project)
        file_menu.add_separator()
        file_menu.add_command(label="Export Selected Message(s)…", command=self._export_selected_messages)
        file_menu.add_command(label="Export Messages…", command=self._export_messages)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_exit)
        menubar.add_cascade(label="File", menu=file_menu)

        view_menu = tk.Menu(menubar, tearoff=False)
        view_menu.add_command(label="Toggle Sidebar", command=self._toggle_sidebar)
        view_menu.add_command(label="Toggle Log Panel", command=self._toggle_log_panel)
        menubar.add_cascade(label="View", menu=view_menu)

        self._theme_var = tk.StringVar(value=load_theme_name())
        theme_menu = tk.Menu(menubar, tearoff=False)
        for theme in THEMES:
            theme_menu.add_radiobutton(
                label=theme.name,
                value=theme.name,
                variable=self._theme_var,
                command=lambda name=theme.name: self._apply_theme(name),  # type: ignore[misc]
            )
        menubar.add_cascade(label="Theme", menu=theme_menu)

        self.configure(menu=menubar)
        self.protocol("WM_DELETE_WINDOW", self._on_exit)

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
        header.pack(fill=tk.X, padx=8, pady=(8, 4))
        ttk.Button(header, text="☰", width=3, command=self._toggle_sidebar).pack(side=tk.LEFT, padx=(0, 8))
        self._project_label_var = tk.StringVar(value="No project selected")
        ttk.Label(header, textvariable=self._project_label_var, font=("Rubik", 14, "bold")).pack(side=tk.LEFT)
        ttk.Button(header, text="Configure Endpoint…", command=self._configure_endpoint).pack(side=tk.RIGHT, padx=4)
        ttk.Button(header, text="Save", command=self._save_current_project).pack(side=tk.RIGHT, padx=4)

        ttk.Separator(right, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=8, pady=(0, 4))

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

    def _apply_theme(self, name: str) -> None:
        theme = get_theme(name)
        self._theme_var.set(theme.name)
        self.configure(bg=theme.bg)
        border_color = get_border_color(theme)

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background=theme.bg, foreground=theme.fg)
        style.configure("TFrame", background=theme.bg)
        style.configure("TLabel", background=theme.bg, foreground=theme.fg)
        style.configure("TButton", background=theme.pane_bg, foreground=theme.fg, padding=(8, 4))
        style.map("TButton", background=[("active", theme.accent), ("!active", theme.pane_bg)])
        style.configure("TEntry", fieldbackground=theme.pane_bg, foreground=theme.fg, insertcolor=theme.fg)
        style.configure("TMenubutton", background=theme.pane_bg, foreground=theme.fg, padding=(6, 3))
        style.configure("TPanedwindow", background=border_color)
        style.configure("TScrollbar", background=theme.pane_bg, troughcolor=theme.bg)
        style.configure("Horizontal.TSeparator", background=border_color)

        for text_widget in (self.editor_pane.text, self.log_panel.text):
            text_widget.configure(
                bg=theme.pane_bg,
                fg=theme.pane_fg,
                insertbackground=theme.pane_fg,
                selectbackground=theme.select_bg,
                selectforeground=theme.select_fg,
            )
        self.editor_pane.listbox.configure(
            bg=theme.pane_bg,
            fg=theme.pane_fg,
            selectbackground=theme.select_bg,
            selectforeground=theme.select_fg,
        )

        self.editor_pane.apply_theme(theme)
        self.sidebar.apply_theme(theme)
        save_theme_name(theme.name)

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
            self.editor_pane.set_messages([])
            self._set_project_controls_enabled(False)
        self._refresh_sidebar()

    def _load_project(self, project: Project) -> None:
        self.current_project = project
        self._dirty = False
        self._project_label_var.set(project.name)
        self.editor_pane.set_messages(project.messages)
        self.send_controls._repeat_var.set(str(project.repeat_count))  # noqa: SLF001
        self.send_controls._delay_var.set(str(project.delay_ms))  # noqa: SLF001
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
        dialog = EndpointDialog(self, self.current_project.endpoint)
        self.wait_window(dialog)
        if dialog.result is not None:
            self.current_project.endpoint = dialog.result
            self._mark_dirty()
            self._save_current_project()

    def _run_selected_projects(self, selected_names: list[str]) -> None:
        """Run all selected projects in batch mode."""
        if not selected_names:
            messagebox.showinfo("Ultra7", "No projects selected. Check projects to run them.")
            return

        # Load selected projects
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

        # Run in background thread
        self._batch_cancel_event = threading.Event()
        self._batch_queue: queue.Queue[tuple[str | None, SendResult | None]] = queue.Queue()

        self._batch_worker = threading.Thread(
            target=self._batch_send_worker, args=(projects,), daemon=True
        )
        self._batch_worker.start()
        self.after(100, self._poll_batch_queue)

    def _batch_send_worker(self, projects: list[Project]) -> None:
        """Background worker that sends messages for all projects."""
        try:
            for project in projects:
                if self._batch_cancel_event.is_set():
                    return

                self._batch_queue.put((f"\n=== Running: {project.name} ===", None))

                # Filter enabled messages
                messages = [m for m in project.messages if m.enabled]
                if not messages:
                    self._batch_queue.put(("No enabled messages", None))
                    continue

                # Get appropriate sender
                try:
                    sender = get_sender(project.endpoint.kind)
                except ValueError:
                    self._batch_queue.put(("Invalid endpoint type", None))
                    continue

                # Send messages with repeat/delay
                for repeat_index in range(project.repeat_count):
                    if self._batch_cancel_event.is_set():
                        return

                    for message in messages:
                        if self._batch_cancel_event.is_set():
                            return

                        # Apply iteration if configured
                        outgoing = message
                        if message.iteration is not None:
                            content = apply_iteration(message.content, message.iteration, repeat_index)
                            outgoing = replace(message, content=content)

                        label = f"  {message.name} [{repeat_index + 1}/{project.repeat_count}]"
                        self._batch_queue.put((label, None))

                        try:
                            result = sender.send(project.endpoint, outgoing)
                        except Exception as exc:
                            result = SendResult(ok=False, latency_ms=0.0, response_summary="", error=str(exc))

                        self._batch_queue.put((label, result))

                if project.delay_ms and project.repeat_count > 1:
                    time.sleep(project.delay_ms / 1000)

        finally:
            self._batch_queue.put((None, None))

    def _poll_batch_queue(self) -> None:
        """Poll results from batch send worker."""
        try:
            while True:
                name, result = self._batch_queue.get_nowait()
                if name is None:
                    self._batch_worker = None  # type: ignore
                    return
                if result is None:
                    self._log_info(name)
                else:
                    self._log_result(name, result)
        except queue.Empty:
            pass
        if self._batch_worker is not None:
            self.after(100, self._poll_batch_queue)

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

    def _on_exit(self) -> None:
        self._save_if_dirty()
        self.destroy()


def main() -> None:
    app = Ultra7App()
    app.mainloop()


if __name__ == "__main__":
    main()
