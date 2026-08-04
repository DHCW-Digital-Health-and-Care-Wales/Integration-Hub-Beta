"""PROMS Transformer Tester — a local dev GUI.

Paste or type a WPAS XML message in the left pane, click **Transform**, and the
FHIR R4B JSON bundle appears in the right pane. Errors (parse failures, routing
errors, validation errors) are shown in the status bar at the bottom.

Run with:
    cd my_tools/proms_tester
    uv run python app.py
"""

from __future__ import annotations

import json
import tkinter as tk
from tkinter import filedialog, font, messagebox, ttk

from xml_fhir_proms_transformer.proms_transformer import transform_proms_xml_to_fhir_bundle


# ---------------------------------------------------------------------------
# Sample XML stubs — quick-load buttons so you don't have to type from scratch
# ---------------------------------------------------------------------------

SAMPLE_OPI = """\
<?xml version="1.0" encoding="UTF-8"?>
<OPI>
  <SYSTEM_ID>108</SYSTEM_ID>
  <DHA_CODE>7A3</DHA_CODE>
  <UNIQUE_ID>EPISODE-00123</UNIQUE_ID>
  <NHS_NUMBER>9434765919</NHS_NUMBER>
  <NHS_CERTIFICATION>01</NHS_CERTIFICATION>
  <UNIT_NUMBER>SB0099887</UNIT_NUMBER>
  <SURNAME>Bevan</SURNAME>
  <FORENAME>Aneurin</FORENAME>
  <SEX>1</SEX>
  <BIRTHDATE>1897-11-15</BIRTHDATE>
  <POSTCODE>SA1 1AA</POSTCODE>
  <SPEC>110</SPEC>
  <SPEC_NAME>Trauma and Orthopaedics</SPEC_NAME>
  <CONS_NAME>Dr James Chess</CONS_NAME>
  <CONS_GMC>1234567</CONS_GMC>
  <UPI_EVENT>OP01</UPI_EVENT>
  <UPI_EVENT_DESC>Outpatient attendance</UPI_EVENT_DESC>
  <UPI_EVENT_DATE>2026-03-04</UPI_EVENT_DATE>
</OPI>
"""

SAMPLE_RFI = """\
<?xml version="1.0" encoding="UTF-8"?>
<RFI>
  <SYSTEM_ID>140</SYSTEM_ID>
  <DHA_CODE>7A7</DHA_CODE>
  <UNIQUE_ID>EPISODE-00456</UNIQUE_ID>
  <NHS_NUMBER>9434765927</NHS_NUMBER>
  <NHS_CERTIFICATION>01</NHS_CERTIFICATION>
  <UNIT_NUMBER>CAV0044556</UNIT_NUMBER>
  <SURNAME>Aneurin</SURNAME>
  <FORENAME>Gareth</FORENAME>
  <SEX>1</SEX>
  <BIRTHDATE>1970-06-21</BIRTHDATE>
  <POSTCODE>CF14 4XW</POSTCODE>
  <SPEC>110</SPEC>
  <SPEC_NAME>Trauma and Orthopaedics</SPEC_NAME>
  <REFERRING_GP>G7654321</REFERRING_GP>
  <UPI_EVENT>OP01</UPI_EVENT>
  <UPI_EVENT_DESC>Outpatient attendance</UPI_EVENT_DESC>
</RFI>
"""

SAMPLE_MPA = """\
<?xml version="1.0" encoding="UTF-8"?>
<MPA>
  <SYSTEM_ID>108</SYSTEM_ID>
  <DHA_CODE>7A3</DHA_CODE>
  <NHS_NUMBER>9434765919</NHS_NUMBER>
  <NHS_CERTIFICATION>01</NHS_CERTIFICATION>
  <UNIT_NUMBER>SB0099887</UNIT_NUMBER>
  <SURNAME>Bevan</SURNAME>
  <FORENAME>Aneurin</FORENAME>
  <SEX>1</SEX>
  <BIRTHDATE>1897-11-15</BIRTHDATE>
  <POSTCODE>SA1 1AA</POSTCODE>
  <DEATHDATE></DEATHDATE>
</MPA>
"""

SAMPLES = {"OPI (Outpatient)": SAMPLE_OPI, "RFI (Referral)": SAMPLE_RFI, "MPA (Patient Update)": SAMPLE_MPA}

# DHCW brand colours
DHCW_NAVY = "#1B294A"
DHCW_BLUE = "#12A3C9"
DHCW_YELLOW = "#F8CA4D"
NHS_BLUE = "#325083"
BG = "#F5F7FA"
PANE_BG = "#FFFFFF"
ERROR_FG = "#C0392B"
OK_FG = "#1A7A3F"


class PromsTestApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("PROMS FHIR Transformer Tester")
        self.configure(bg=BG)
        self.geometry("1400x860")
        self.minsize(900, 600)
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        mono = font.Font(family="Consolas", size=10)
        label_font = font.Font(family="Segoe UI", size=9, weight="bold")
        header_font = font.Font(family="Segoe UI", size=11, weight="bold")
        btn_font = font.Font(family="Segoe UI", size=10, weight="bold")

        # ── Header bar ──────────────────────────────────────────────────
        header = tk.Frame(self, bg=DHCW_NAVY, height=50)
        header.pack(fill=tk.X)
        tk.Label(
            header,
            text="  WPAS → PROMS FHIR Transformer Tester",
            bg=DHCW_NAVY,
            fg=DHCW_YELLOW,
            font=header_font,
            anchor="w",
        ).pack(side=tk.LEFT, fill=tk.Y, pady=8)
        tk.Label(
            header,
            text="DHCW Integration Hub  ",
            bg=DHCW_NAVY,
            fg=DHCW_BLUE,
            font=font.Font(family="Segoe UI", size=9),
            anchor="e",
        ).pack(side=tk.RIGHT, fill=tk.Y, pady=8)

        # ── Toolbar ─────────────────────────────────────────────────────
        toolbar = tk.Frame(self, bg=NHS_BLUE, pady=6)
        toolbar.pack(fill=tk.X)

        tk.Label(toolbar, text="  Load sample:", bg=NHS_BLUE, fg="white",
                 font=font.Font(family="Segoe UI", size=9)).pack(side=tk.LEFT, padx=(6, 2))
        for label, xml in SAMPLES.items():
            tk.Button(
                toolbar, text=label,
                bg=DHCW_BLUE, fg="white", activebackground=DHCW_YELLOW,
                font=font.Font(family="Segoe UI", size=9), relief=tk.FLAT,
                padx=8, pady=2,
                command=lambda x=xml: self._load_sample(x),
            ).pack(side=tk.LEFT, padx=3)

        tk.Frame(toolbar, bg=NHS_BLUE).pack(side=tk.LEFT, expand=True)

        tk.Button(
            toolbar, text="📂  Open XML file…",
            bg="#2C3E6F", fg="white", activebackground=DHCW_YELLOW,
            font=font.Font(family="Segoe UI", size=9), relief=tk.FLAT,
            padx=8, pady=2,
            command=self._open_file,
        ).pack(side=tk.LEFT, padx=3)

        tk.Button(
            toolbar, text="💾  Save JSON…",
            bg="#2C3E6F", fg="white", activebackground=DHCW_YELLOW,
            font=font.Font(family="Segoe UI", size=9), relief=tk.FLAT,
            padx=8, pady=2,
            command=self._save_json,
        ).pack(side=tk.LEFT, padx=3)

        tk.Button(
            toolbar, text="🗑  Clear",
            bg="#2C3E6F", fg="white", activebackground=DHCW_YELLOW,
            font=font.Font(family="Segoe UI", size=9), relief=tk.FLAT,
            padx=8, pady=2,
            command=self._clear,
        ).pack(side=tk.LEFT, padx=(3, 12))

        # ── Main content: two panes + divider ───────────────────────────
        content = tk.Frame(self, bg=BG)
        content.pack(fill=tk.BOTH, expand=True, padx=10, pady=(8, 0))

        paned = ttk.PanedWindow(content, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # Left pane — XML input
        left = tk.Frame(paned, bg=BG)
        paned.add(left, weight=1)

        tk.Label(left, text="WPAS XML Input", bg=BG, fg=DHCW_NAVY, font=label_font, anchor="w").pack(
            fill=tk.X, padx=4, pady=(4, 2)
        )
        input_frame = tk.Frame(left, bg=PANE_BG, relief=tk.SOLID, bd=1)
        input_frame.pack(fill=tk.BOTH, expand=True, padx=4)

        self._input_text = tk.Text(
            input_frame, font=mono, wrap=tk.NONE, bg=PANE_BG, fg="#1B1B1B",
            insertbackground=DHCW_NAVY, selectbackground=DHCW_BLUE, selectforeground="white",
            undo=True, relief=tk.FLAT, padx=6, pady=6,
        )
        in_vscroll = ttk.Scrollbar(input_frame, orient=tk.VERTICAL, command=self._input_text.yview)
        in_hscroll = ttk.Scrollbar(input_frame, orient=tk.HORIZONTAL, command=self._input_text.xview)
        self._input_text.configure(yscrollcommand=in_vscroll.set, xscrollcommand=in_hscroll.set)
        in_vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        in_hscroll.pack(side=tk.BOTTOM, fill=tk.X)
        self._input_text.pack(fill=tk.BOTH, expand=True)

        # Right pane — JSON output
        right = tk.Frame(paned, bg=BG)
        paned.add(right, weight=1)

        tk.Label(right, text="FHIR R4B JSON Output", bg=BG, fg=DHCW_NAVY, font=label_font, anchor="w").pack(
            fill=tk.X, padx=4, pady=(4, 2)
        )
        output_frame = tk.Frame(right, bg=PANE_BG, relief=tk.SOLID, bd=1)
        output_frame.pack(fill=tk.BOTH, expand=True, padx=4)

        self._output_text = tk.Text(
            output_frame, font=mono, wrap=tk.NONE, bg=PANE_BG, fg="#1B1B1B",
            insertbackground=DHCW_NAVY, selectbackground=DHCW_BLUE, selectforeground="white",
            state=tk.DISABLED, relief=tk.FLAT, padx=6, pady=6,
        )
        out_vscroll = ttk.Scrollbar(output_frame, orient=tk.VERTICAL, command=self._output_text.yview)
        out_hscroll = ttk.Scrollbar(output_frame, orient=tk.HORIZONTAL, command=self._output_text.xview)
        self._output_text.configure(yscrollcommand=out_vscroll.set, xscrollcommand=out_hscroll.set)
        out_vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        out_hscroll.pack(side=tk.BOTTOM, fill=tk.X)
        self._output_text.pack(fill=tk.BOTH, expand=True)

        # ── Transform button ────────────────────────────────────────────
        btn_bar = tk.Frame(self, bg=BG, pady=8)
        btn_bar.pack(fill=tk.X, padx=10)

        self._transform_btn = tk.Button(
            btn_bar,
            text="▶  Transform",
            bg=DHCW_BLUE, fg="white", activebackground=DHCW_YELLOW, activeforeground=DHCW_NAVY,
            font=btn_font, relief=tk.FLAT, padx=24, pady=6,
            cursor="hand2",
            command=self._transform,
        )
        self._transform_btn.pack(side=tk.LEFT)
        # Keyboard shortcut
        self.bind("<Return>", lambda _e: self._transform())
        self.bind("<KP_Enter>", lambda _e: self._transform())
        self.bind("<Control-Return>", lambda _e: self._transform())

        self._status_var = tk.StringVar(value="Ready — paste a WPAS XML message or load a sample.")
        self._status_label = tk.Label(
            btn_bar, textvariable=self._status_var,
            bg=BG, fg="#555555",
            font=font.Font(family="Segoe UI", size=9),
            anchor="w",
        )
        self._status_label.pack(side=tk.LEFT, padx=16, fill=tk.X, expand=True)

        # ── Status / size bar ───────────────────────────────────────────
        footer = tk.Frame(self, bg=DHCW_NAVY, height=22)
        footer.pack(fill=tk.X, side=tk.BOTTOM)
        self._size_var = tk.StringVar(value="")
        tk.Label(footer, textvariable=self._size_var, bg=DHCW_NAVY, fg=DHCW_BLUE,
                 font=font.Font(family="Segoe UI", size=8), anchor="e").pack(
            side=tk.RIGHT, padx=8, pady=2
        )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _load_sample(self, xml: str) -> None:
        self._set_input(xml)
        self._set_status("Sample loaded — click Transform (or press Enter) to convert.", ok=True)

    def _set_input(self, text: str) -> None:
        self._input_text.delete("1.0", tk.END)
        self._input_text.insert("1.0", text.strip())

    def _open_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Open WPAS XML file",
            filetypes=[("XML files", "*.xml"), ("All files", "*.*")],
        )
        if path:
            try:
                with open(path, encoding="utf-8") as fh:
                    self._set_input(fh.read())
                self._set_status(f"Loaded: {path}", ok=True)
            except OSError as exc:
                self._set_status(f"Could not open file: {exc}", ok=False)

    def _save_json(self) -> None:
        content = self._output_text.get("1.0", tk.END).strip()
        if not content:
            messagebox.showinfo("Nothing to save", "Transform a message first.")
            return
        path = filedialog.asksaveasfilename(
            title="Save FHIR JSON",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(content)
                self._set_status(f"Saved: {path}", ok=True)
            except OSError as exc:
                self._set_status(f"Could not save file: {exc}", ok=False)

    def _clear(self) -> None:
        self._input_text.delete("1.0", tk.END)
        self._set_output("")
        self._set_status("Cleared.", ok=True)
        self._size_var.set("")

    def _transform(self) -> None:
        xml = self._input_text.get("1.0", tk.END).strip()
        if not xml:
            self._set_status("Nothing to transform — paste a WPAS XML message first.", ok=False)
            return

        self._set_status("Transforming…", ok=True)
        self.update_idletasks()

        try:
            bundle = transform_proms_xml_to_fhir_bundle(xml)
            raw_json = bundle.model_dump_json()
            pretty = json.dumps(json.loads(raw_json), indent=2, ensure_ascii=False)
            self._set_output(pretty)
            entry_count = len(bundle.entry or [])
            resource_types = [e.resource.get_resource_type() for e in (bundle.entry or [])]
            summary = f"✓  {entry_count} entries: {', '.join(resource_types)}"
            self._set_status(summary, ok=True)
            self._size_var.set(f"{len(raw_json):,} bytes  |  {entry_count} entries")
        except ValueError as exc:
            self._set_output("")
            self._set_status(f"✗  {exc}", ok=False)
            self._size_var.set("")
        except Exception as exc:  # noqa: BLE001 — surface unexpected errors to the dev
            self._set_output("")
            self._set_status(f"✗  Unexpected error: {exc}", ok=False)
            self._size_var.set("")

    def _set_output(self, text: str) -> None:
        self._output_text.configure(state=tk.NORMAL)
        self._output_text.delete("1.0", tk.END)
        if text:
            self._output_text.insert("1.0", text)
        self._output_text.configure(state=tk.DISABLED)

    def _set_status(self, message: str, *, ok: bool) -> None:
        self._status_var.set(message)
        self._status_label.configure(fg=OK_FG if ok else ERROR_FG)


if __name__ == "__main__":
    app = PromsTestApp()
    app.mainloop()
