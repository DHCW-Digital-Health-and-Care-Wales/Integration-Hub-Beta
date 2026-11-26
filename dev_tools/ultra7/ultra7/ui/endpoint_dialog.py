"""Modal dialog for configuring a project's endpoint (MLLP / REST / SOAP)."""
from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk

from ultra7.models import Endpoint
from ultra7.senders.connectivity import INTEGRATION_HUB_PRESETS, test_endpoint_connection
from ultra7.ui.themes import DEFAULT_THEME_NAME, Theme, get_border_color, get_semantic_colors, get_theme


class EndpointDialog(tk.Toplevel):
    """Blocking dialog that edits a copy of an Endpoint. Result in `self.result`."""

    def __init__(self, parent: tk.Misc, endpoint: Endpoint, theme: Theme | None = None) -> None:
        super().__init__(parent)
        self.title("Configure Endpoint")
        self.resizable(False, False)
        self.transient(parent)  # type: ignore[call-overload]
        self.result: Endpoint | None = None
        self._theme = theme or get_theme(DEFAULT_THEME_NAME)
        if theme is not None:
            self.configure(bg=theme.bg)

        self._kind = tk.StringVar(value=endpoint.kind)
        self._host = tk.StringVar(value=endpoint.host)
        self._port = tk.StringVar(value=str(endpoint.port) if endpoint.port else "")
        self._url = tk.StringVar(value=endpoint.url)
        self._soap_action = tk.StringVar(value=endpoint.soap_action)
        self._timeout = tk.StringVar(value=str(endpoint.timeout_seconds))
        self._headers_text = "\n".join(f"{k}: {v}" for k, v in endpoint.headers.items())
        self._preset_map = {name: ep for name, ep in INTEGRATION_HUB_PRESETS}

        # Title area.
        ttk.Label(self, text="Configure Endpoint", font=("Rubik", 12, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 8)
        )

        row = 1
        ttk.Label(self, text="Preset", style="Muted.TLabel").grid(row=row, column=0, sticky="w", padx=12, pady=4)
        self._preset_var = tk.StringVar(value="— Choose Integration Hub preset —")
        preset_menu = ttk.OptionMenu(
            self,
            self._preset_var,
            self._preset_var.get(),
            *self._preset_map.keys(),
            command=self._apply_preset,  # type: ignore[arg-type]
        )
        preset_menu.grid(row=row, column=1, sticky="ew", padx=12, pady=4)
        row += 1

        ttk.Label(self, text="Kind").grid(row=row, column=0, sticky="w", padx=12, pady=4)
        kind_menu = ttk.OptionMenu(
            self, self._kind, endpoint.kind, "mllp", "rest", "soap", command=self._on_kind_change  # type: ignore[arg-type]
        )
        kind_menu.grid(row=row, column=1, sticky="ew", padx=12, pady=4)
        row += 1

        self._host_label = ttk.Label(self, text="Host")
        self._host_label.grid(row=row, column=0, sticky="w", padx=12, pady=4)
        self._host_entry = ttk.Entry(self, textvariable=self._host)
        self._host_entry.grid(row=row, column=1, sticky="ew", padx=12, pady=4)
        row += 1

        self._port_label = ttk.Label(self, text="Port")
        self._port_label.grid(row=row, column=0, sticky="w", padx=12, pady=4)
        self._port_entry = ttk.Entry(self, textvariable=self._port)
        self._port_entry.grid(row=row, column=1, sticky="ew", padx=12, pady=4)
        row += 1

        self._url_label = ttk.Label(self, text="URL")
        self._url_label.grid(row=row, column=0, sticky="w", padx=12, pady=4)
        self._url_entry = ttk.Entry(self, textvariable=self._url, width=40)
        self._url_entry.grid(row=row, column=1, sticky="ew", padx=12, pady=4)
        row += 1

        self._soap_label = ttk.Label(self, text="SOAPAction")
        self._soap_label.grid(row=row, column=0, sticky="w", padx=12, pady=4)
        self._soap_entry = ttk.Entry(self, textvariable=self._soap_action)
        self._soap_entry.grid(row=row, column=1, sticky="ew", padx=12, pady=4)
        row += 1

        ttk.Label(self, text="Timeout (s)").grid(row=row, column=0, sticky="w", padx=12, pady=4)
        ttk.Entry(self, textvariable=self._timeout).grid(row=row, column=1, sticky="ew", padx=12, pady=4)
        row += 1

        ttk.Separator(self, orient=tk.HORIZONTAL).grid(
            row=row, column=0, columnspan=2, sticky="ew", padx=12, pady=(8, 4)
        )
        row += 1
        ttk.Label(self, text="Headers (one 'Name: Value' per line)").grid(
            row=row, column=0, columnspan=2, sticky="w", padx=12, pady=(4, 0)
        )
        row += 1
        self._headers_box = tk.Text(
            self, width=40, height=4, font=("Menlo", 10), bd=0, padx=6, pady=6, highlightthickness=1
        )
        if theme is not None:
            self._headers_box.configure(
                bg=theme.pane_bg,
                fg=theme.pane_fg,
                insertbackground=theme.pane_fg,
                selectbackground=theme.select_bg,
                selectforeground=theme.select_fg,
                highlightbackground=get_border_color(theme),
                highlightcolor=theme.accent,
            )
        self._headers_box.insert("1.0", self._headers_text)
        self._headers_box.grid(row=row, column=0, columnspan=2, sticky="ew", padx=12, pady=4)
        row += 1

        ttk.Separator(self, orient=tk.HORIZONTAL).grid(
            row=row, column=0, columnspan=2, sticky="ew", padx=12, pady=(4, 0)
        )
        row += 1
        test_row = ttk.Frame(self)
        test_row.grid(row=row, column=0, columnspan=2, sticky="ew", padx=12, pady=(8, 0))
        self._test_btn = ttk.Button(test_row, text="Test Connection", command=self._run_connection_test)
        self._test_btn.pack(side=tk.LEFT)
        self._test_status_var = tk.StringVar(value="")
        self._test_status_label = ttk.Label(test_row, textvariable=self._test_status_var, style="Muted.TLabel")
        self._test_status_label.pack(side=tk.LEFT, padx=(10, 0))
        row += 1

        button_row = ttk.Frame(self)
        button_row.grid(row=row, column=0, columnspan=2, pady=12)
        ttk.Button(button_row, text="Cancel", command=self._cancel).pack(side=tk.LEFT, padx=4)
        ttk.Button(button_row, text="Save", style="Accent.TButton", command=self._save).pack(side=tk.LEFT, padx=4)

        self._on_kind_change(endpoint.kind)
        self.grab_set()

    def _apply_preset(self, name: str) -> None:
        preset = self._preset_map.get(name)
        if preset is None:
            return
        self._kind.set(preset.kind)
        self._host.set(preset.host)
        self._port.set(str(preset.port) if preset.port else "")
        self._url.set(preset.url)
        self._soap_action.set(preset.soap_action)
        self._timeout.set(str(preset.timeout_seconds))
        self._on_kind_change(preset.kind)

    def _build_endpoint(self) -> Endpoint:
        kind = self._kind.get()
        port_text = self._port.get().strip()
        port: int | None = None
        if kind == "mllp" and port_text:
            try:
                port = int(port_text)
            except ValueError:
                port = None
        try:
            timeout_seconds = float(self._timeout.get())
        except ValueError:
            timeout_seconds = 5.0

        return Endpoint(
            kind=kind,  # type: ignore[arg-type]
            host=self._host.get().strip(),
            port=port,
            url=self._url.get().strip(),
            headers=self._parse_headers(),
            soap_action=self._soap_action.get().strip(),
            timeout_seconds=timeout_seconds,
        )

    def _run_connection_test(self) -> None:
        endpoint = self._build_endpoint()
        self._test_btn.configure(state="disabled")
        self._test_status_var.set("Testing…")

        def _worker() -> None:
            try:
                ok, latency_ms, detail = test_endpoint_connection(endpoint)
            except Exception as exc:  # noqa: BLE001 — always restore the Test Connection button
                ok, latency_ms, detail = False, 0.0, str(exc)
            if self.winfo_exists():
                self.after(0, lambda: self._finish_connection_test(ok, latency_ms, detail))

        threading.Thread(target=_worker, daemon=True).start()

    def _finish_connection_test(self, ok: bool, latency_ms: float, detail: str) -> None:
        if not self.winfo_exists():
            return
        self._test_btn.configure(state="normal")
        colors = get_semantic_colors(self._theme)
        self._test_status_label.configure(foreground=colors["ok"] if ok else colors["error"])
        prefix = "✓" if ok else "✗"
        self._test_status_var.set(f"{prefix} {detail} ({latency_ms:.1f} ms)")

    def _on_kind_change(self, kind: str) -> None:
        is_mllp = kind == "mllp"
        for widget in (self._host_label, self._host_entry, self._port_label, self._port_entry):
            widget.configure(state="normal" if is_mllp else "disabled")
        for widget in (self._url_label, self._url_entry):
            widget.configure(state="disabled" if is_mllp else "normal")
        soap_state = "normal" if kind == "soap" else "disabled"
        self._soap_label.configure(state=soap_state)
        self._soap_entry.configure(state=soap_state)

    def _parse_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        for line in self._headers_box.get("1.0", tk.END).splitlines():
            if not line.strip() or ":" not in line:
                continue
            name, value = line.split(":", 1)
            headers[name.strip()] = value.strip()
        return headers

    def _save(self) -> None:
        self.result = self._build_endpoint()
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()
