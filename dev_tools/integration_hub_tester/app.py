"""Component Tester — multi-service developer GUI.

Each service page hosts one Integration Hub service. All service pages share
the same ServicePage widget (input pane, output pane, sample dropdown,
toolbar). The service-specific logic lives entirely in the ServicePlugin
subclasses in the services/ package — adding a new service means adding one
file there and registering it in PLUGIN_CATEGORIES below.

Services are grouped into categories (Transformers/Servers/Senders), shown
via a left-hand sidebar; the content area shows the selected category's
services as an underline-style tab strip, similar to common desktop dev
tools (e.g. Podman Desktop). A light/dark theme toggle is available in the
header (see THEMES).

Run with:
    cd dev_tools/integration_hub_tester
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
from services.core_reference_plugin import CoreReferencePlugin
from services.hl7_sender_ack_plugin import Hl7SenderAckPlugin
from services.hl7_sender_plugin import Hl7SenderPlugin
from services.hl7_server_plugin import Hl7ServerPlugin
from services.hl7_soap_server_plugin import HL7SoapServerPlugin
from services.mock_receiver_manager import MockReceiverManager
from services.phw_plugin import PhwPlugin
from services.pims_plugin import PimsPlugin
from services.proms_plugin import PromsPlugin
from services.rest_server_plugin import RestServerPlugin
from services.soap_sender_plugin import SoapSenderPlugin
from services.soap_subscription_sender_plugin import SoapSubscriptionSenderPlugin

phw_plugin = PhwPlugin()
chemo_plugin = ChemoPlugin()
pims_plugin = PimsPlugin()
core_reference_plugin = CoreReferencePlugin()
proms_plugin = PromsPlugin()
hl7_server_plugin = Hl7ServerPlugin()
hl7_sender_plugin = Hl7SenderPlugin()
hl7_sender_ack_plugin = Hl7SenderAckPlugin()
rest_server_plugin = RestServerPlugin()
hl7_soap_server_plugin = HL7SoapServerPlugin()
soap_sender_plugin = SoapSenderPlugin()
soap_subscription_sender_plugin = SoapSubscriptionSenderPlugin()

PLUGINS: list[ServicePlugin] = [
    phw_plugin,
    chemo_plugin,
    pims_plugin,
    core_reference_plugin,
    proms_plugin,
    hl7_server_plugin,
    hl7_sender_plugin,
    hl7_sender_ack_plugin,
    rest_server_plugin,
    hl7_soap_server_plugin,
    soap_sender_plugin,
    soap_subscription_sender_plugin,
]

# Category groupings for the top-level notebook, mirroring the repo's
# transformers/servers/senders top-level folders. Each category becomes one
# top-level tab containing its own sub-notebook — this keeps the top-level
# tab bar at a fixed, small width no matter how many individual services get
# added over time (a flat one-tab-per-service bar would eventually run off
# the edge of the window).
PLUGIN_CATEGORIES: list[tuple[str, list[ServicePlugin]]] = [
    ("🔧 Transformers", [phw_plugin, chemo_plugin, pims_plugin, core_reference_plugin, proms_plugin]),
    ("🖥 Servers", [hl7_server_plugin, rest_server_plugin, hl7_soap_server_plugin]),
    ("📤 Senders", [hl7_sender_plugin, hl7_sender_ack_plugin, soap_sender_plugin, soap_subscription_sender_plugin]),
]

# ── DHCW brand colours & theme palettes ─────────────────────────────────────
# Brand accent colours (blue/yellow) stay constant across both themes for
# recognisability; backgrounds, text and status colours flip between the two
# palettes below. Toggle via the "🌓 Theme" button in the header.
THEMES: dict[str, dict[str, str]] = {
    "light": {
        "navy": "#1B294A",
        "blue": "#12A3C9",
        "yellow": "#F8CA4D",
        "nhs_blue": "#325083",
        "bg": "#F5F7FA",
        "pane_bg": "#FFFFFF",
        "text_fg": "#1B1B1B",
        "muted_fg": "#555555",
        "error_fg": "#C0392B",
        "ok_fg": "#1A7A3F",
        "footer_fg": "#5A7A9A",
        "mock_bar_bg": "#0F1E38",
        "sidebar_bg": "#EDEFF3",
        "sidebar_fg": "#3A4A63",
        "hover_bg": "#E2E8F0",
    },
    "dark": {
        "navy": "#0B111F",
        "blue": "#12A3C9",
        "yellow": "#F8CA4D",
        "nhs_blue": "#25344F",
        "bg": "#1B2130",
        "pane_bg": "#242C3D",
        "text_fg": "#E7ECF3",
        "muted_fg": "#9AA7BD",
        "error_fg": "#FF6B5B",
        "ok_fg": "#4CD97B",
        "footer_fg": "#6D88A8",
        "mock_bar_bg": "#0A1220",
        "sidebar_bg": "#14171F",
        "sidebar_fg": "#9AA7BD",
        "hover_bg": "#232838",
    },
}

_current_theme_name = "light"


def current_theme() -> dict[str, str]:
    """Return the active theme's colour dict. Read at widget-build time only —
    switching themes rebuilds the whole widget tree rather than reconfiguring
    individual widgets (see IntegrationHubTesterApp._toggle_theme)."""
    return THEMES[_current_theme_name]


class _AutoHideScrollbar(ttk.Scrollbar):
    """A ttk.Scrollbar that hides itself when its content already fits fully
    in view, and reappears once scrolling becomes possible.

    Requires the scrollbar to be placed with grid() — it toggles visibility
    via grid_remove()/grid() in response to the (lo, hi) fractions Tk's Text
    widget reports through the standard scrollcommand protocol.
    """

    def set(self, lo: str, hi: str) -> None:
        if float(lo) <= 0.0 and float(hi) >= 1.0:
            self.grid_remove()
        else:
            self.grid()
        super().set(lo, hi)


class ServicePage(tk.Frame):
    """A reusable panel that drives any ServicePlugin.

    All tabs share this exact widget. The only thing that varies between
    tabs is the plugin instance — layout, buttons and error handling are
    identical across all services.
    """

    def __init__(self, parent: tk.Widget, plugin: ServicePlugin) -> None:
        self._theme = current_theme()
        super().__init__(parent, bg=self._theme["bg"])
        self._plugin = plugin
        self._build()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build(self) -> None:
        t = self._theme
        mono = font.Font(family="Consolas", size=10)
        label_font = font.Font(family="Segoe UI", size=9, weight="bold")
        btn_font = font.Font(family="Segoe UI", size=9, weight="bold")

        # ── Description bar ────────────────────────────────────────────
        desc_bar = tk.Frame(self, bg=t["nhs_blue"], pady=4)
        desc_bar.pack(fill=tk.X)
        tk.Label(
            desc_bar, text=f"  {self._plugin.description}",
            bg=t["nhs_blue"], fg="white",
            font=font.Font(family="Segoe UI", size=9),
            anchor="w",
        ).pack(side=tk.LEFT, padx=4)

        # ── Sample / file toolbar ──────────────────────────────────────
        toolbar = tk.Frame(self, bg=t["bg"], pady=5)
        toolbar.pack(fill=tk.X, padx=8)

        # A dropdown (rather than one button per sample) keeps the toolbar a
        # fixed width no matter how many samples a plugin registers — some
        # tabs (e.g. PROMS) now have 9+ and a button-per-sample row would run
        # off the edge of the window.
        if self._plugin.samples:
            tk.Label(toolbar, text="Load sample:", bg=t["bg"], fg=t["text_fg"],
                     font=font.Font(family="Segoe UI", size=9)).pack(side=tk.LEFT, padx=(0, 4))
            sample_labels = list(self._plugin.samples.keys())
            self._sample_var = tk.StringVar(value=sample_labels[0])
            sample_box = ttk.Combobox(
                toolbar, textvariable=self._sample_var, values=sample_labels,
                state="readonly", width=42, font=font.Font(family="Segoe UI", size=9),
            )
            sample_box.pack(side=tk.LEFT, padx=(0, 4))
            sample_box.bind("<<ComboboxSelected>>", self._on_sample_selected)
            # Flat "link-style" button — only the main action button below
            # keeps a solid colour fill, per the flattened toolbar look.
            tk.Button(
                toolbar, text="Load",
                bg=t["bg"], fg=t["blue"], activebackground=t["hover_bg"], activeforeground=t["blue"],
                font=font.Font(family="Segoe UI", size=8, weight="bold"), relief=tk.FLAT, bd=0,
                padx=10, pady=2, cursor="hand2",
                command=self._load_selected_sample,
            ).pack(side=tk.LEFT, padx=2)

        tk.Frame(toolbar, bg=t["bg"]).pack(side=tk.LEFT, expand=True)

        for text, cmd in (
            ("📂 Open…", self._open_file),
            ("💾 Save…", self._save_output),
            ("🗑 Clear", self._clear),
        ):
            tk.Button(
                toolbar, text=text,
                bg=t["bg"], fg=t["muted_fg"], activebackground=t["hover_bg"], activeforeground=t["blue"],
                font=font.Font(family="Segoe UI", size=8), relief=tk.FLAT, bd=0, cursor="hand2",
                padx=7, pady=2,
                command=cmd,
            ).pack(side=tk.LEFT, padx=2)

        # ── Two-pane area ──────────────────────────────────────────────
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 4))

        def _pane(parent: ttk.PanedWindow, label_text: str, editable: bool) -> tk.Text:
            frame = tk.Frame(parent, bg=t["bg"])
            parent.add(frame, weight=1)
            tk.Label(frame, text=label_text, bg=t["bg"], fg=t["text_fg"],
                     font=label_font, anchor="w").pack(fill=tk.X, pady=(2, 2))
            box = tk.Frame(frame, bg=t["pane_bg"], relief=tk.SOLID, bd=1)
            box.pack(fill=tk.BOTH, expand=True)
            box.rowconfigure(0, weight=1)
            box.columnconfigure(0, weight=1)
            text = tk.Text(
                box, font=mono, wrap=tk.NONE,
                bg=t["pane_bg"], fg=t["text_fg"],
                insertbackground=t["text_fg"],
                selectbackground=t["blue"], selectforeground="white",
                state=tk.NORMAL if editable else tk.DISABLED,
                relief=tk.FLAT, padx=6, pady=6, undo=editable,
            )
            # Scrollbars only appear once content actually overflows the pane
            # (see _AutoHideScrollbar) — grid (not pack) is required so they
            # can grid_remove() themselves.
            vs = _AutoHideScrollbar(box, orient=tk.VERTICAL, command=text.yview)
            hs = _AutoHideScrollbar(box, orient=tk.HORIZONTAL, command=text.xview)
            text.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
            text.grid(row=0, column=0, sticky="nsew")
            vs.grid(row=0, column=1, sticky="ns")
            hs.grid(row=1, column=0, sticky="ew")
            return text

        self._input = _pane(paned, self._plugin.input_label, editable=True)
        self._output = _pane(paned, self._plugin.output_label, editable=False)

        # ── Action row ─────────────────────────────────────────────────
        action = tk.Frame(self, bg=t["bg"], pady=5)
        action.pack(fill=tk.X, padx=8)

        tk.Button(
            action,
            text=self._plugin.button_label,
            bg=t["blue"], fg="white",
            activebackground=t["yellow"], activeforeground=t["navy"],
            font=btn_font, relief=tk.FLAT, padx=20, pady=5, cursor="hand2",
            command=self._run,
        ).pack(side=tk.LEFT)

        self._status_var = tk.StringVar(value="Ready.")
        self._status_lbl = tk.Label(
            action, textvariable=self._status_var,
            bg=t["bg"], fg=t["muted_fg"], font=font.Font(family="Segoe UI", size=9), anchor="w",
        )
        self._status_lbl.pack(side=tk.LEFT, padx=12, fill=tk.X, expand=True)

        self._size_var = tk.StringVar(value="")
        tk.Label(action, textvariable=self._size_var, bg=t["bg"], fg=t["blue"],
                 font=font.Font(family="Segoe UI", size=8)).pack(side=tk.RIGHT)

        # Keyboard shortcut: Enter triggers the action button from this tab.
        self.bind_all("<Control-Return>", lambda _e: self._run() if self.winfo_ismapped() else None)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _load_sample(self, content: str) -> None:
        self._set_input(content)
        self._set_status("Sample loaded — press the action button to run.", ok=True)

    def _load_selected_sample(self) -> None:
        label = self._sample_var.get()
        content = self._plugin.samples.get(label)
        if content is not None:
            self._load_sample(content)

    def _on_sample_selected(self, _event: object = None) -> None:
        # Selecting a new value in the dropdown loads it immediately —
        # no need for a separate click on "Load" as well.
        self._load_selected_sample()

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
        self._status_lbl.configure(fg=self._theme["ok_fg"] if ok else self._theme["error_fg"])


class IntegrationHubTesterApp(tk.Tk):
    """Main application window.

    Layout mirrors a typical desktop dev tool (e.g. Podman Desktop): a
    left-hand sidebar lists service categories (Transformers/Servers/
    Senders); the content area shows the selected category's services as an
    underline-style tab strip, with the matching ServicePage below it.
    """

    def __init__(self) -> None:
        super().__init__()
        self.title("Int Hub Component Tester")
        self.geometry("1500x900")
        self.minsize(1000, 640)
        self._mock_manager = MockReceiverManager()
        self._build()
        # Ensure any running mock receiver is stopped when the window is closed.
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build(self) -> None:
        t = current_theme()
        self.configure(bg=t["navy"])
        hf = font.Font(family="Segoe UI", size=11, weight="bold")

        # Remember the current selection across rebuilds (theme toggle) —
        # these are plain instance attributes so they survive the
        # destroy-and-rebuild in _toggle_theme without needing to be
        # captured/restored explicitly.
        if not hasattr(self, "_selected_category"):
            self._selected_category = PLUGIN_CATEGORIES[0][0]
        if not hasattr(self, "_selected_service"):
            self._selected_service = {cat: plugins[0].tab_label for cat, plugins in PLUGIN_CATEGORIES}

        # ── Header ────────────────────────────────────────────────────
        # Two rows: title / theme toggle on row 1, Mock Receiver controls
        # (right-aligned, under the theme toggle) on row 2.
        header = tk.Frame(self, bg=t["navy"])
        header.pack(fill=tk.X)

        header_row1 = tk.Frame(header, bg=t["navy"], height=52)
        header_row1.pack(fill=tk.X)
        tk.Label(
            header_row1, text="  DHCW Integration Hub — Component Tester",
            bg=t["navy"], fg=t["blue"], font=hf, anchor="w",
        ).pack(side=tk.LEFT, fill=tk.Y, pady=10)

        theme_btn_text = "☀  Light mode" if _current_theme_name == "dark" else "🌙  Dark mode"
        tk.Button(
            header_row1, text=theme_btn_text,
            bg=t["navy"], fg=t["blue"], activebackground=t["yellow"], activeforeground=t["navy"],
            font=font.Font(family="Segoe UI", size=9, weight="bold"), relief=tk.FLAT,
            padx=10, pady=2, cursor="hand2",
            command=self._toggle_theme,
        ).pack(side=tk.RIGHT, padx=(0, 10), pady=10)
        tk.Label(
            header_row1, text="LOCAL DEV TOOL ",
            bg=t["navy"], fg=t["blue"],
            font=font.Font(family="Segoe UI", size=9),
        ).pack(side=tk.RIGHT, fill=tk.Y, pady=10)

        # ── Mock Receiver control bar (header row 2, right-aligned) ─────
        self._build_mock_receiver_bar(header)

        # ttk styling shared by the sample-dropdown Combobox (the only ttk
        # widget left now that the notebook has been replaced by the
        # sidebar/underline-tab layout below).
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TCombobox",
                         fieldbackground=t["pane_bg"], background=t["pane_bg"],
                         foreground=t["text_fg"], arrowcolor=t["text_fg"])
        style.map("TCombobox", fieldbackground=[("readonly", t["pane_bg"])])

        # ── Body: sidebar (left) + content area (right) ─────────────────
        body = tk.Frame(self, bg=t["bg"])
        body.pack(fill=tk.BOTH, expand=True)

        sidebar = tk.Frame(body, bg=t["sidebar_bg"], width=220)
        sidebar.pack(side=tk.LEFT, fill=tk.Y)
        sidebar.pack_propagate(False)  # keep a fixed sidebar width regardless of content

        content = tk.Frame(body, bg=t["bg"])
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        content.rowconfigure(0, weight=1)
        content.columnconfigure(0, weight=1)

        sidebar_font = font.Font(family="Segoe UI", size=10)
        tab_font = font.Font(family="Segoe UI", size=9, weight="bold")

        self._sidebar_items: dict[str, tk.Label] = {}
        self._category_containers: dict[str, tk.Frame] = {}
        # Per category: {service tab_label: (label widget, underline bar)}
        self._service_tabs: dict[str, dict[str, tuple[tk.Label, tk.Frame]]] = {}
        # Per category: {service tab_label: ServicePage}
        self._service_pages: dict[str, dict[str, ServicePage]] = {}

        tk.Frame(sidebar, bg=t["sidebar_bg"], height=8).pack(fill=tk.X)  # top breathing room

        for category_label, plugins in PLUGIN_CATEGORIES:
            # Sidebar nav item
            item = tk.Label(
                sidebar, text=f"  {category_label}", bg=t["sidebar_bg"], fg=t["sidebar_fg"],
                font=sidebar_font, anchor="w", padx=6, pady=10, cursor="hand2",
            )
            item.pack(fill=tk.X, padx=8, pady=1)
            item.bind("<Button-1>", lambda _e, cat=category_label: self._select_category(cat))
            self._sidebar_items[category_label] = item

            # Category content: underline tab strip + a stack of ServicePages
            # (one per service), only the selected one raised to the top.
            category_container = tk.Frame(content, bg=t["bg"])
            category_container.grid(row=0, column=0, sticky="nsew")
            category_container.rowconfigure(1, weight=1)
            category_container.columnconfigure(0, weight=1)
            self._category_containers[category_label] = category_container

            tab_strip = tk.Frame(category_container, bg=t["bg"])
            tab_strip.grid(row=0, column=0, sticky="ew")
            divider = tk.Frame(category_container, bg=t["hover_bg"], height=1)
            divider.grid(row=0, column=0, sticky="sew")

            stack_area = tk.Frame(category_container, bg=t["bg"])
            stack_area.grid(row=1, column=0, sticky="nsew")
            stack_area.rowconfigure(0, weight=1)
            stack_area.columnconfigure(0, weight=1)

            self._service_tabs[category_label] = {}
            self._service_pages[category_label] = {}

            for plugin in plugins:
                tab_cell = tk.Frame(tab_strip, bg=t["bg"])
                tab_cell.pack(side=tk.LEFT)
                tab_lbl = tk.Label(
                    tab_cell, text=plugin.tab_label, bg=t["bg"], fg=t["muted_fg"],
                    font=tab_font, cursor="hand2", padx=14, pady=8,
                )
                tab_lbl.pack(side=tk.TOP)
                underline = tk.Frame(tab_cell, bg=t["bg"], height=2)
                underline.pack(side=tk.TOP, fill=tk.X)
                for widget in (tab_cell, tab_lbl):
                    widget.bind(
                        "<Button-1>",
                        lambda _e, cat=category_label, svc=plugin.tab_label: self._select_service(cat, svc),
                    )
                self._service_tabs[category_label][plugin.tab_label] = (tab_lbl, underline)

                page = ServicePage(stack_area, plugin)
                page.grid(row=0, column=0, sticky="nsew")
                self._service_pages[category_label][plugin.tab_label] = page

        # Restore (or default to) the previously-selected category/service.
        self._select_category(self._selected_category)
        for category_label, _plugins in PLUGIN_CATEGORIES:
            self._select_service(category_label, self._selected_service[category_label], _raise_category=False)

        # ── Status footer ─────────────────────────────────────────────
        footer = tk.Frame(self, bg=t["navy"], height=22)
        footer.pack(fill=tk.X, side=tk.BOTTOM)
        tk.Label(
            footer,
            text="  Ctrl+Return = run action on active tab  |  Changes to transformer source files take effect immediately",
            bg=t["navy"], fg=t["footer_fg"],
            font=font.Font(family="Segoe UI", size=8),
            anchor="w",
        ).pack(side=tk.LEFT, padx=6, pady=2)

    def _select_category(self, category_label: str) -> None:
        """Switch the visible category, highlighting its sidebar entry."""
        t = current_theme()
        self._selected_category = category_label
        for cat, item in self._sidebar_items.items():
            active = cat == category_label
            item.configure(
                bg=t["hover_bg"] if active else t["sidebar_bg"],
                fg=t["blue"] if active else t["sidebar_fg"],
            )
        self._category_containers[category_label].tkraise()

    def _select_service(self, category_label: str, tab_label: str, *, _raise_category: bool = True) -> None:
        """Switch the visible service page within a category's tab strip."""
        t = current_theme()
        self._selected_service[category_label] = tab_label
        for label, (lbl_widget, underline) in self._service_tabs[category_label].items():
            active = label == tab_label
            lbl_widget.configure(fg=t["blue"] if active else t["muted_fg"])
            underline.configure(bg=t["blue"] if active else t["bg"])
        self._service_pages[category_label][tab_label].tkraise()
        if _raise_category:
            self._select_category(category_label)

    def _toggle_theme(self) -> None:
        """Flip the light/dark theme and rebuild the whole widget tree.

        Colours are only read at build time (see current_theme()), so the
        simplest reliable way to re-theme every widget is to tear down and
        rebuild — this is a small, local dev tool, so the rebuild cost is
        negligible. The currently-selected category/service is restored
        afterwards (via the persisted _selected_category/_selected_service
        instance attributes) so the toggle doesn't lose the user's place.
        Any unsaved input/output text in the tabs is reset by the rebuild.
        """
        global _current_theme_name

        _current_theme_name = "dark" if _current_theme_name == "light" else "light"

        for child in self.winfo_children():
            child.destroy()
        self._build()

    # ── Mock Receiver control bar ──────────────────────────────────────────

    def _build_mock_receiver_bar(self, parent: tk.Frame) -> None:
        """Build the persistent mock receiver launch/stop toolbar.

        Lives as row 2 of the header, right-aligned under the theme toggle —
        buttons first, status indicator last, so reading left-to-right ends
        on the current state.
        """
        t = current_theme()
        bar = tk.Frame(parent, bg=t["mock_bar_bg"], pady=5)
        bar.pack(fill=tk.X)

        btn_font = font.Font(family="Segoe UI", size=8, weight="bold")
        lbl_font = font.Font(family="Segoe UI", size=8)

        # Packed side=RIGHT in this order so the visual order (left-to-right)
        # is: Start MLLP, Start SOAP, Stop, Mock Receiver: <status>.
        # Status indicator — updated by _poll_mock_receiver_status
        self._mock_status_var = tk.StringVar(value="● Stopped")
        self._mock_status_lbl = tk.Label(
            bar, textvariable=self._mock_status_var,
            bg=t["mock_bar_bg"], fg="#E05050",
            font=lbl_font, width=12, anchor="w",
        )
        self._mock_status_lbl.pack(side=tk.RIGHT, padx=(2, 8))

        tk.Label(
            bar, text="Mock Receiver:",
            bg=t["mock_bar_bg"], fg=t["yellow"],
            font=btn_font,
        ).pack(side=tk.RIGHT, padx=(8, 2))

        # Stop button
        tk.Button(
            bar, text="■  Stop",
            bg="#7B3030", fg="white", activebackground=t["yellow"], activeforeground=t["navy"],
            font=btn_font, relief=tk.FLAT, padx=9, pady=2, cursor="hand2",
            command=self._stop_mock,
        ).pack(side=tk.RIGHT, padx=2)

        # Start SOAP button
        tk.Button(
            bar, text="▶  Start SOAP Mock",
            bg=t["blue"], fg="white", activebackground=t["yellow"], activeforeground=t["navy"],
            font=btn_font, relief=tk.FLAT, padx=9, pady=2, cursor="hand2",
            command=lambda: self._start_mock("soap"),
        ).pack(side=tk.RIGHT, padx=2)

        # Start MLLP button
        tk.Button(
            bar, text="▶  Start MLLP Mock",
            bg=t["nhs_blue"], fg="white", activebackground=t["yellow"], activeforeground=t["navy"],
            font=btn_font, relief=tk.FLAT, padx=9, pady=2, cursor="hand2",
            command=lambda: self._start_mock("mllp"),
        ).pack(side=tk.RIGHT, padx=(10, 2))

        # Begin polling process status every 2 seconds.
        self._poll_mock_receiver_status()

    def _start_mock(self, mode: str) -> None:
        success, message = self._mock_manager.start(mode)
        self._update_mock_status()
        if not success:
            from tkinter import messagebox
            messagebox.showwarning("Mock Receiver", message)

    def _stop_mock(self) -> None:
        self._mock_manager.stop()
        self._update_mock_status()

    def _update_mock_status(self) -> None:
        label = self._mock_manager.label
        self._mock_status_var.set(label)
        running = self._mock_manager.is_running
        self._mock_status_lbl.configure(fg="#2ECC71" if running else "#E05050")

    def _poll_mock_receiver_status(self) -> None:
        """Check if the mock receiver process is still alive every 2 seconds."""
        self._update_mock_status()
        self.after(2000, self._poll_mock_receiver_status)

    def _on_close(self) -> None:
        """Stop any running mock receiver before closing the window."""
        self._mock_manager.stop()
        self.destroy()


if __name__ == "__main__":
    app = IntegrationHubTesterApp()
    app.mainloop()
