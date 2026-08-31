"""Modal dialog for configuring a project's endpoint (MLLP / REST / SOAP)."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ultra7.models import Endpoint


class EndpointDialog(tk.Toplevel):
    """Blocking dialog that edits a copy of an Endpoint. Result in `self.result`."""

    def __init__(self, parent: tk.Misc, endpoint: Endpoint) -> None:
        super().__init__(parent)
        self.title("Configure Endpoint")
        self.resizable(False, False)
        self.transient(parent)  # type: ignore[call-overload]
        self.result: Endpoint | None = None

        self._kind = tk.StringVar(value=endpoint.kind)
        self._host = tk.StringVar(value=endpoint.host)
        self._port = tk.StringVar(value=str(endpoint.port) if endpoint.port else "")
        self._url = tk.StringVar(value=endpoint.url)
        self._soap_action = tk.StringVar(value=endpoint.soap_action)
        self._timeout = tk.StringVar(value=str(endpoint.timeout_seconds))
        self._headers_text = "\n".join(f"{k}: {v}" for k, v in endpoint.headers.items())

        # Title area.
        ttk.Label(self, text="Configure Endpoint", font=("Rubik", 12, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 8)
        )

        row = 1
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
        self._headers_box = tk.Text(self, width=40, height=4, font=("Menlo", 10), bd=1, relief="solid")
        self._headers_box.insert("1.0", self._headers_text)
        self._headers_box.grid(row=row, column=0, columnspan=2, sticky="ew", padx=12, pady=4)
        row += 1

        ttk.Separator(self, orient=tk.HORIZONTAL).grid(
            row=row, column=0, columnspan=2, sticky="ew", padx=12, pady=(4, 0)
        )
        row += 1
        button_row = ttk.Frame(self)
        button_row.grid(row=row, column=0, columnspan=2, pady=12)
        ttk.Button(button_row, text="Cancel", command=self._cancel).pack(side=tk.LEFT, padx=4)
        ttk.Button(button_row, text="Save", command=self._save).pack(side=tk.LEFT, padx=4)

        self._on_kind_change(endpoint.kind)
        self.grab_set()

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
        kind = self._kind.get()
        port_text = self._port.get().strip()
        port = int(port_text) if kind == "mllp" and port_text else None
        try:
            timeout_seconds = float(self._timeout.get())
        except ValueError:
            timeout_seconds = 5.0

        self.result = Endpoint(
            kind=kind,  # type: ignore[arg-type]
            host=self._host.get().strip(),
            port=port,
            url=self._url.get().strip(),
            headers=self._parse_headers(),
            soap_action=self._soap_action.get().strip(),
            timeout_seconds=timeout_seconds,
        )
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()
