"""Dialog for configuring a project's endpoint (MLLP / REST / SOAP)."""
from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk

from ultra7.models import Endpoint, EndpointKind, MllpMode
from ultra7.senders.connectivity import INTEGRATION_HUB_PRESETS, test_endpoint_connection
from ultra7.ui.themes import DEFAULT_THEME_NAME, Theme, get_border_color, get_semantic_colors, get_theme

_KIND_LABELS: dict[EndpointKind, str] = {
    "mllp": "MLLP (HL7 over TCP)",
    "rest": "REST (HTTP / HTTPS POST)",
    "soap": "SOAP (XML over HTTP / HTTPS)",
}
_LABEL_TO_KIND: dict[str, EndpointKind] = {label: kind for kind, label in _KIND_LABELS.items()}

_MLLP_MODE_LABELS: dict[MllpMode, str] = {
    "per_message": "Per message (new TCP connection)",
    "stream": "Persistent stream (single TCP connection)",
    "pipelined": "Pipelined burst (all frames on 1 stream)",
}
_MLLP_LABEL_TO_MODE: dict[str, MllpMode] = {label: mode for mode, label in _MLLP_MODE_LABELS.items()}


class EndpointDialog(tk.Toplevel):
    """Configures a copy of an Endpoint with protocol-specific fields and validation.

    Result is stored in ``self.result`` when saved, or ``None`` if cancelled.
    """

    def __init__(self, parent: tk.Misc, endpoint: Endpoint, theme: Theme | None = None) -> None:
        super().__init__(parent)
        self.title("Configure Endpoint")
        self.resizable(False, False)
        self.transient(parent)  # type: ignore[call-overload]
        self.result: Endpoint | None = None
        self._theme = theme or get_theme(DEFAULT_THEME_NAME)
        self.configure(bg=self._theme.bg)

        self._kind_label = tk.StringVar(value=_KIND_LABELS.get(endpoint.kind, _KIND_LABELS["mllp"]))
        default_mode_label = _MLLP_MODE_LABELS.get(endpoint.mllp_mode, _MLLP_MODE_LABELS["per_message"])
        self._mllp_mode_label = tk.StringVar(value=default_mode_label)
        self._host = tk.StringVar(value=endpoint.host)
        self._port = tk.StringVar(value=str(endpoint.port) if endpoint.port else "")
        self._url = tk.StringVar(value=endpoint.url)
        self._soap_action = tk.StringVar(value=endpoint.soap_action)
        self._timeout = tk.StringVar(value=str(endpoint.timeout_seconds))
        self._headers_text = "\n".join(f"{k}: {v}" for k, v in endpoint.headers.items())
        self._preset_map = {name: ep for name, ep in INTEGRATION_HUB_PRESETS}

        body = ttk.Frame(self, padding=14)
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(1, weight=1)

        ttk.Label(body, text="Configure Endpoint", font=("Rubik", 12, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 4)
        )
        subtitle = (
            "Choose a preset below or enter connection details for this flow."
            if not endpoint.is_configured
            else "Edit connection details or switch protocol / MLLP streaming mode."
        )
        ttk.Label(body, text=subtitle, style="Muted.TLabel").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )

        # -- Preset & Protocol selectors (readonly Combobox avoids macOS OptionMenu freezes) --
        ttk.Label(body, text="Preset", style="Muted.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=4)
        self._preset_var = tk.StringVar(value="")
        preset_combo = ttk.Combobox(
            body,
            textvariable=self._preset_var,
            values=tuple(self._preset_map.keys()),
            state="readonly",
            width=36,
        )
        preset_combo.grid(row=2, column=1, sticky="ew", pady=4)
        preset_combo.bind("<<ComboboxSelected>>", lambda _e: self._apply_preset(self._preset_var.get()))

        ttk.Label(body, text="Protocol").grid(row=3, column=0, sticky="w", padx=(0, 10), pady=4)
        kind_combo = ttk.Combobox(
            body,
            textvariable=self._kind_label,
            values=tuple(_KIND_LABELS.values()),
            state="readonly",
            width=36,
        )
        kind_combo.grid(row=3, column=1, sticky="ew", pady=4)
        kind_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_kind_change())

        # -- MLLP fields ------------------------------------------------------
        self._host_label = ttk.Label(body, text="Host")
        self._host_entry = ttk.Entry(body, textvariable=self._host)

        self._port_label = ttk.Label(body, text="Port")
        self._port_entry = ttk.Entry(body, textvariable=self._port)

        self._mllp_mode_lbl = ttk.Label(body, text="MLLP Mode")
        self._mllp_mode_combo = ttk.Combobox(
            body,
            textvariable=self._mllp_mode_label,
            values=tuple(_MLLP_MODE_LABELS.values()),
            state="readonly",
            width=36,
        )

        # -- REST / SOAP fields -----------------------------------------------
        self._url_label = ttk.Label(body, text="URL")
        self._url_entry = ttk.Entry(body, textvariable=self._url, width=40)

        self._soap_label = ttk.Label(body, text="SOAPAction")
        self._soap_entry = ttk.Entry(body, textvariable=self._soap_action)

        # -- Common timeout ---------------------------------------------------
        ttk.Label(body, text="Timeout (s)").grid(row=9, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(body, textvariable=self._timeout).grid(row=9, column=1, sticky="ew", pady=4)

        # -- HTTP headers (only shown for REST / SOAP) ------------------------
        self._headers_sep = ttk.Separator(body, orient=tk.HORIZONTAL)
        self._headers_label = ttk.Label(body, text="Headers (one 'Name: Value' per line)", style="Muted.TLabel")
        self._headers_box = tk.Text(
            body,
            width=40,
            height=4,
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
        self._headers_box.insert("1.0", self._headers_text)

        # -- Validation + Test Connection + Action buttons --------------------
        ttk.Separator(body, orient=tk.HORIZONTAL).grid(row=13, column=0, columnspan=2, sticky="ew", pady=(8, 6))

        self._error_var = tk.StringVar(value="")
        self._error_label = ttk.Label(body, textvariable=self._error_var, wraplength=420)
        self._error_label.grid(row=14, column=0, columnspan=2, sticky="w", pady=(0, 4))

        test_row = ttk.Frame(body)
        test_row.grid(row=15, column=0, columnspan=2, sticky="ew", pady=(2, 4))
        self._test_btn = ttk.Button(test_row, text="Test Connection", command=self._run_connection_test)
        self._test_btn.pack(side=tk.LEFT)
        self._test_status_var = tk.StringVar(value="")
        self._test_status_label = ttk.Label(test_row, textvariable=self._test_status_var, style="Muted.TLabel")
        self._test_status_label.pack(side=tk.LEFT, padx=(10, 0))

        button_row = ttk.Frame(body)
        button_row.grid(row=16, column=0, columnspan=2, pady=(10, 0))
        ttk.Button(button_row, text="Cancel", command=self._cancel).pack(side=tk.LEFT, padx=4)
        ttk.Button(button_row, text="Save", style="Accent.TButton", command=self._save).pack(side=tk.LEFT, padx=4)

        self._on_kind_change()
        self.bind("<Escape>", lambda _e: self._cancel())
        self.lift()
        self.focus_set()

    def _current_kind(self) -> EndpointKind:
        return _LABEL_TO_KIND.get(self._kind_label.get(), "mllp")

    def _apply_preset(self, name: str) -> None:
        preset = self._preset_map.get(name)
        if preset is None:
            return
        self._kind_label.set(_KIND_LABELS.get(preset.kind, _KIND_LABELS["mllp"]))
        self._mllp_mode_label.set(_MLLP_MODE_LABELS.get(preset.mllp_mode, _MLLP_MODE_LABELS["per_message"]))
        self._host.set(preset.host)
        self._port.set(str(preset.port) if preset.port else "")
        self._url.set(preset.url)
        self._soap_action.set(preset.soap_action)
        self._timeout.set(str(preset.timeout_seconds))
        self._error_var.set("")
        self._on_kind_change()

    def _validate_and_build(self) -> tuple[Endpoint | None, str | None]:
        kind = self._current_kind()
        try:
            timeout_seconds = float(self._timeout.get().strip())
        except ValueError:
            return None, "Timeout must be a positive number (e.g. 5.0)."
        if timeout_seconds <= 0:
            return None, "Timeout must be greater than 0."

        if kind == "mllp":
            host = self._host.get().strip()
            port_text = self._port.get().strip()
            if not host:
                return None, "Host is required for MLLP (e.g. 127.0.0.1)."
            try:
                port = int(port_text)
            except ValueError:
                return None, "Port must be an integer between 1 and 65535 (e.g. 2575)."
            if not (1 <= port <= 65535):
                return None, "Port must be between 1 and 65535."
            return (
                Endpoint(
                    kind="mllp",
                    host=host,
                    port=port,
                    url="",
                    headers={},
                    soap_action="",
                    timeout_seconds=timeout_seconds,
                    mllp_mode=_MLLP_LABEL_TO_MODE.get(self._mllp_mode_label.get(), "per_message"),
                ),
                None,
            )

        url = self._url.get().strip()
        scheme, sep, rest = url.partition("://")
        if not (sep and scheme.lower() in ("http", "https") and rest.strip()):
            return None, "URL must start with http:// or https:// (e.g. http://127.0.0.1:8084/ingest)."

        return (
            Endpoint(
                kind=kind,
                host="",
                port=None,
                url=url,
                headers=self._parse_headers(),
                soap_action=self._soap_action.get().strip() if kind == "soap" else "",
                timeout_seconds=timeout_seconds,
                mllp_mode="per_message",
            ),
            None,
        )

    def _run_connection_test(self) -> None:
        endpoint, error = self._validate_and_build()
        if error or endpoint is None:
            colors = get_semantic_colors(self._theme)
            self._error_label.configure(foreground=colors["error"])
            self._error_var.set(f"⚠ {error}")
            return
        self._error_var.set("")
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

    def _on_kind_change(self) -> None:
        kind = self._current_kind()
        for widget in (
            self._host_label,
            self._host_entry,
            self._port_label,
            self._port_entry,
            self._mllp_mode_lbl,
            self._mllp_mode_combo,
            self._url_label,
            self._url_entry,
            self._soap_label,
            self._soap_entry,
            self._headers_sep,
            self._headers_label,
            self._headers_box,
        ):
            widget.grid_remove()

        if kind == "mllp":
            self._host_label.grid(row=4, column=0, sticky="w", padx=(0, 10), pady=4)
            self._host_entry.grid(row=4, column=1, sticky="ew", pady=4)
            self._port_label.grid(row=5, column=0, sticky="w", padx=(0, 10), pady=4)
            self._port_entry.grid(row=5, column=1, sticky="ew", pady=4)
            self._mllp_mode_lbl.grid(row=6, column=0, sticky="w", padx=(0, 10), pady=4)
            self._mllp_mode_combo.grid(row=6, column=1, sticky="ew", pady=4)
        else:
            self._url_label.grid(row=4, column=0, sticky="w", padx=(0, 10), pady=4)
            self._url_entry.grid(row=4, column=1, sticky="ew", pady=4)
            if kind == "soap":
                self._soap_label.grid(row=5, column=0, sticky="w", padx=(0, 10), pady=4)
                self._soap_entry.grid(row=5, column=1, sticky="ew", pady=4)
            self._headers_sep.grid(row=10, column=0, columnspan=2, sticky="ew", pady=(8, 4))
            self._headers_label.grid(row=11, column=0, columnspan=2, sticky="w", pady=(2, 2))
            self._headers_box.grid(row=12, column=0, columnspan=2, sticky="ew", pady=4)

        self._error_var.set("")

    def _parse_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        for line in self._headers_box.get("1.0", tk.END).splitlines():
            if not line.strip() or ":" not in line:
                continue
            name, value = line.split(":", 1)
            headers[name.strip()] = value.strip()
        return headers

    def _save(self) -> None:
        endpoint, error = self._validate_and_build()
        if error or endpoint is None:
            colors = get_semantic_colors(self._theme)
            self._error_label.configure(foreground=colors["error"])
            self._error_var.set(f"⚠ {error}")
            return
        self.result = endpoint
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()
