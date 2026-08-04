"""Integration Hub Tester — multi-service developer GUI.

Each tab hosts one Integration Hub service. All tabs share the same
ServicePage widget (input pane, output pane, sample buttons, toolbar).
The service-specific logic lives entirely in the ServicePlugin subclasses
in the services/ package — adding a new service means adding one file there
and registering it in PLUGINS below.

Run with:
    cd my_tools/integration_hub_tester
    uv run python app.py
"""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, font, ttk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.base import ServicePlugin

# ── Plugin registry ────────────────────────────────────────────────────────
# Import order = tab order.  Add new services here only.
from services.chemo_plugin import ChemoPlugin
from services.hl7_sender_plugin import Hl7SenderPlugin
from services.hl7_server_plugin import Hl7ServerPlugin
from services.phw_plugin import PhwPlugin
from services.pims_plugin import PimsPlugin
from services.proms_plugin import PromsPlugin

PLUGINS: list[ServicePlugin] = [
    PhwPlugin(),
    ChemoPlugin(),
    PimsPlugin(),
    PromsPlugin(),
    Hl7ServerPlugin(),
    Hl7SenderPlugin(),
]

# ── DHCW brand colours ──────────────────────────────────────────────────────
DHCW_NAVY = "#1B294A"
DHCW_BLUE = "#12A3C9"
DHCW_YELLOW = "#F8CA4D"
NHS_BLUE = "#325083"
BG = "#F5F7FA"
PANE_BG = "#FFFFFF"
ERROR_FG = "#C0392B"
OK_FG = "#1A7A3F"


class ServicePage(tk.Frame):
    """A reusable panel that drives any ServicePlugin.

    All tabs share this exact widget. The only thing that varies between
    tabs is the plugin instance — layout, buttons and error handling are
    identical across all services.
    """

    def __init__(self, parent: tk.Widget, plugin: ServicePlugin) -> None:
        super().__init__(parent, bg=BG)
        self._plugin = plugin
        self._build()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build(self) -> None:
        mono = font.Font(family="Consolas", size=10)
        label_font = font.Font(family="Segoe UI", size=9, weight="bold")
        btn_font = font.Font(family="Segoe UI", size=9, weight="bold")

        # ── Description bar ────────────────────────────────────────────
        desc_bar = tk.Frame(self, bg=NHS_BLUE, pady=4)
        desc_bar.pack(fill=tk.X)
        tk.Label(
            desc_bar, text=f"  {self._plugin.description}",
            bg=NHS_BLUE, fg="white",
            font=font.Font(family="Segoe UI", size=9),
            anchor="w",
        ).pack(side=tk.LEFT, padx=4)

        # ── Sample / file toolbar ──────────────────────────────────────
        toolbar = tk.Frame(self, bg=BG, pady=5)
        toolbar.pack(fill=tk.X, padx=8)

        if self._plugin.samples:
            tk.Label(toolbar, text="Load sample:", bg=BG, fg=DHCW_NAVY,
                     font=font.Font(family="Segoe UI", size=9)).pack(side=tk.LEFT, padx=(0, 4))
            for label, content in self._plugin.samples.items():
                tk.Button(
                    toolbar, text=label,
                    bg=DHCW_BLUE, fg="white", activebackground=DHCW_YELLOW,
                    font=font.Font(family="Segoe UI", size=8), relief=tk.FLAT,
                    padx=7, pady=2,
                    command=lambda c=content: self._load_sample(c),
                ).pack(side=tk.LEFT, padx=2)

        tk.Frame(toolbar, bg=BG).pack(side=tk.LEFT, expand=True)

        for text, cmd in (
            ("📂 Open…", self._open_file),
            ("💾 Save…", self._save_output),
            ("🗑 Clear", self._clear),
        ):
            tk.Button(
                toolbar, text=text,
                bg="#2C3E6F", fg="white", activebackground=DHCW_YELLOW,
                font=font.Font(family="Segoe UI", size=8), relief=tk.FLAT,
                padx=7, pady=2,
                command=cmd,
            ).pack(side=tk.LEFT, padx=2)

        # ── Two-pane area ──────────────────────────────────────────────
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 4))

        def _pane(parent: tk.Widget, label_text: str, editable: bool) -> tk.Text:
            frame = tk.Frame(parent, bg=BG)
            parent.add(frame, weight=1)
            tk.Label(frame, text=label_text, bg=BG, fg=DHCW_NAVY,
                     font=label_font, anchor="w").pack(fill=tk.X, pady=(2, 2))
            box = tk.Frame(frame, bg=PANE_BG, relief=tk.SOLID, bd=1)
            box.pack(fill=tk.BOTH, expand=True)
            text = tk.Text(
                box, font=mono, wrap=tk.NONE,
                bg=PANE_BG, fg="#1B1B1B",
                insertbackground=DHCW_NAVY,
                selectbackground=DHCW_BLUE, selectforeground="white",
                state=tk.NORMAL if editable else tk.DISABLED,
                relief=tk.FLAT, padx=6, pady=6, undo=editable,
            )
            vs = ttk.Scrollbar(box, orient=tk.VERTICAL, command=text.yview)
            hs = ttk.Scrollbar(box, orient=tk.HORIZONTAL, command=text.xview)
            text.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
            vs.pack(side=tk.RIGHT, fill=tk.Y)
            hs.pack(side=tk.BOTTOM, fill=tk.X)
            text.pack(fill=tk.BOTH, expand=True)
            return text

        self._input = _pane(paned, self._plugin.input_label, editable=True)
        self._output = _pane(paned, self._plugin.output_label, editable=False)

        # ── Action row ─────────────────────────────────────────────────
        action = tk.Frame(self, bg=BG, pady=5)
        action.pack(fill=tk.X, padx=8)

        tk.Button(
            action,
            text=self._plugin.button_label,
            bg=DHCW_BLUE, fg="white",
            activebackground=DHCW_YELLOW, activeforeground=DHCW_NAVY,
            font=btn_font, relief=tk.FLAT, padx=20, pady=5, cursor="hand2",
            command=self._run,
        ).pack(side=tk.LEFT)

        self._status_var = tk.StringVar(value="Ready.")
        self._status_lbl = tk.Label(
            action, textvariable=self._status_var,
            bg=BG, fg="#555", font=font.Font(family="Segoe UI", size=9), anchor="w",
        )
        self._status_lbl.pack(side=tk.LEFT, padx=12, fill=tk.X, expand=True)

        self._size_var = tk.StringVar(value="")
        tk.Label(action, textvariable=self._size_var, bg=BG, fg=DHCW_BLUE,
                 font=font.Font(family="Segoe UI", size=8)).pack(side=tk.RIGHT)

        # Keyboard shortcut: Enter triggers the action button from this tab.
        self.bind_all("<Control-Return>", lambda _e: self._run() if self.winfo_ismapped() else None)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _load_sample(self, content: str) -> None:
        self._set_input(content)
        self._set_status("Sample loaded — press the action button to run.", ok=True)

    def _set_input(self, text: str) -> None:
        self._input.delete("1.0", tk.END)
        self._input.insert("1.0", text.strip())

    def _open_file(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("HL7 / XML / JSON", "*.hl7 *.xml *.json *.txt"), ("All files", "*.*")]
        )
        if path:
            try:
                with open(path, encoding="utf-8") as fh:
                    self._set_input(fh.read())
                self._set_status(f"Loaded: {path}", ok=True)
            except OSError as exc:
                self._set_status(f"Could not open: {exc}", ok=False)

    def _save_output(self) -> None:
        content = self._output.get("1.0", tk.END).strip()
        if not content:
            self._set_status("Nothing to save — run the action first.", ok=False)
            return
        # Guess an appropriate extension from the output content.
        ext = ".json" if content.lstrip().startswith("{") else ".txt"
        path = filedialog.asksaveasfilename(defaultextension=ext,
                                            filetypes=[("Output file", f"*{ext}"), ("All files", "*.*")])
        if path:
            try:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(content)
                self._set_status(f"Saved: {path}", ok=True)
            except OSError as exc:
                self._set_status(f"Could not save: {exc}", ok=False)

    def _clear(self) -> None:
        self._input.delete("1.0", tk.END)
        self._set_output("")
        self._set_status("Cleared.", ok=True)
        self._size_var.set("")

    def _run(self) -> None:
        text = self._input.get("1.0", tk.END).strip()
        if not text:
            self._set_status("Paste or load some input first.", ok=False)
            return

        self._set_status("Running…", ok=True)
        self.update_idletasks()

        try:
            output, summary = self._plugin.run(text)
            self._set_output(output)
            self._set_status(summary, ok=summary.startswith("✓"))
            self._size_var.set(f"{len(output):,} chars")
        except ValueError as exc:
            self._set_output("")
            self._set_status(f"✗  {exc}", ok=False)
            self._size_var.set("")
        except Exception as exc:  # noqa: BLE001
            self._set_output("")
            self._set_status(f"✗  Unexpected error: {type(exc).__name__}: {exc}", ok=False)
            self._size_var.set("")

    def _set_output(self, text: str) -> None:
        self._output.configure(state=tk.NORMAL)
        self._output.delete("1.0", tk.END)
        if text:
            self._output.insert("1.0", text)
        self._output.configure(state=tk.DISABLED)

    def _set_status(self, message: str, *, ok: bool) -> None:
        self._status_var.set(message)
        self._status_lbl.configure(fg=OK_FG if ok else ERROR_FG)


class IntegrationHubTesterApp(tk.Tk):
    """Main application window — a tabbed notebook, one tab per service."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Integration Hub Tester")
        self.configure(bg=DHCW_NAVY)
        self.geometry("1500x900")
        self.minsize(1000, 640)
        self._build()

    def _build(self) -> None:
        hf = font.Font(family="Segoe UI", size=11, weight="bold")

        # ── Header ────────────────────────────────────────────────────
        header = tk.Frame(self, bg=DHCW_NAVY, height=52)
        header.pack(fill=tk.X)
        tk.Label(
            header, text="  DHCW Integration Hub — Service Tester",
            bg=DHCW_NAVY, fg=DHCW_YELLOW, font=hf, anchor="w",
        ).pack(side=tk.LEFT, fill=tk.Y, pady=10)
        tk.Label(
            header, text="Local developer tool — not tracked by git  ",
            bg=DHCW_NAVY, fg=DHCW_BLUE,
            font=font.Font(family="Segoe UI", size=9),
        ).pack(side=tk.RIGHT, fill=tk.Y, pady=10)

        # ── Notebook ──────────────────────────────────────────────────
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook", background=DHCW_NAVY, borderwidth=0)
        style.configure("TNotebook.Tab",
                         background=NHS_BLUE, foreground="white",
                         padding=[14, 6], font=("Segoe UI", 9, "bold"))
        style.map("TNotebook.Tab",
                  background=[("selected", DHCW_BLUE)],
                  foreground=[("selected", "white")])

        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=4, pady=(4, 0))

        for plugin in PLUGINS:
            page = ServicePage(notebook, plugin)
            notebook.add(page, text=f"  {plugin.tab_label}  ")

        # ── Status footer ─────────────────────────────────────────────
        footer = tk.Frame(self, bg=DHCW_NAVY, height=22)
        footer.pack(fill=tk.X, side=tk.BOTTOM)
        tk.Label(
            footer,
            text="  Ctrl+Return = run action on active tab  |  Changes to transformer source files take effect immediately",
            bg=DHCW_NAVY, fg="#5a7a9a",
            font=font.Font(family="Segoe UI", size=8),
            anchor="w",
        ).pack(side=tk.LEFT, padx=6, pady=2)


if __name__ == "__main__":
    app = IntegrationHubTesterApp()
    app.mainloop()
