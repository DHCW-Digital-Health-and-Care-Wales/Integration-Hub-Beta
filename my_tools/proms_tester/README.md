# PROMS Transformer Tester — Developer Tool

A local developer GUI for testing and debugging the **WPAS → PROMS FHIR transformer**
without running a Service Bus queue, container, or any Azure infrastructure.

> **Not tracked by git.** This tool lives in `my_tools/` which is listed in the
> repo-root `.gitignore`. It will never appear in a commit or pull request.

---

## Contents

1. [Quick Start](#1-quick-start)
2. [Running with the VS Code Debugger (breakpoints)](#2-running-with-the-vs-code-debugger-breakpoints)
3. [GUI Features](#3-gui-features)
4. [Architectural Breakdown](#4-architectural-breakdown)
5. [Folder Structure](#5-folder-structure)
6. [How the Transformer Pipeline Works](#6-how-the-transformer-pipeline-works)
7. [Updating the Tool](#7-updating-the-tool)

---

## 1. Quick Start

### Prerequisites

- Python 3.13+
- [`uv`](https://docs.astral.sh/uv/) installed (`pip install uv` or via `winget install astral-sh.uv`)
- The repo cloned locally with `xml_fhir_proms_transformer/` present

### Install & run

```powershell
cd my_tools\proms_tester
uv sync          # creates .venv and installs all dependencies (first time only)
uv run python app.py
```

Or, after the first `uv sync`, you can also launch directly:

```powershell
.venv\Scripts\python.exe app.py
```

The GUI opens immediately — no Azure credentials, no Service Bus connection, no
config file edits required.

---

## 2. Running with the VS Code Debugger (breakpoints)

A **VS Code launch configuration** has been added at
`.vscode/launch.json` in the repo root. It targets this tool's isolated `.venv`
and sets `"justMyCode": false` so the debugger steps into the transformer library
as well as `app.py`.

### Steps

1. Open the repo root in VS Code (`code .` from the repo root, or **File → Open Folder**).
2. Open **Run and Debug** — `Ctrl + Shift + D`.
3. Select **"PROMS Tester GUI"** from the configuration dropdown at the top of the panel.
4. Press **F5** (or click the green ▶ button).
5. The GUI launches. Set breakpoints anywhere:

| Where to set breakpoints | What it lets you inspect |
|---|---|
| `app.py` → `_transform()` | The raw XML string before it is sent to the transformer |
| `xml_fhir_proms_transformer/proms_parser.py` | How the XML is parsed into a flat `PromsMessage` field map |
| `xml_fhir_proms_transformer/message_types.py` → `resolve_message_type()` | Which message type (OPI / RFI / MPA) is selected and why |
| `xml_fhir_proms_transformer/proms_transformer.py` → `build_fhir_bundle()` | UUID allocation, resource assembly, which branch is taken |
| `xml_fhir_proms_transformer/mappers/patient_mapper.py` | Every field mapping for the Patient resource |
| `xml_fhir_proms_transformer/mappers/message_header_mapper.py` | MessageHeader source, event coding, focus list |
| `xml_fhir_proms_transformer/mappers/care_plan_mapper.py` | CarePlan identifier, category (specialty), activity links |
| `xml_fhir_proms_transformer/mappers/task_mapper.py` | EQ5D5L and Data Entry task inputs |
| `xml_fhir_proms_transformer/mappers/participant_mappers.py` | Practitioner GMC identifier, Organisation ODS code |

Click **Transform** in the GUI to trigger the code path. VS Code will pause at
your breakpoint and you can step through with **F10** (step over), **F11** (step
into), and inspect variables in the Watch / Variables panels.

---

## 3. GUI Features

| Feature | Detail |
|---|---|
| **Load sample buttons** | Pre-loads an OPI (Outpatient), RFI (Referral), or MPA (Patient Update) message into the input pane. Use these as a starting point — edit the XML to test specific fields. |
| **Open XML file** | Opens a file picker to load any `.xml` file from disk. Useful once you have real WPAS sample messages. |
| **Transform button** | Runs the full transformer pipeline and displays the FHIR R4B JSON in the right pane. Also triggered by **Enter** or **Ctrl+Enter**. |
| **Save JSON** | Saves the current output to a `.json` file. |
| **Clear** | Empties both panes. |
| **Status bar** | Shows `✓` and a summary of entry resource types on success (e.g. `MessageHeader, CarePlan, Task, Task, Patient, Practitioner, Organization`), or `✗` and the error message on failure. |
| **Footer** | Shows the output size in bytes and entry count after a successful transform. |
| **Undo / redo in the input pane** | Standard `Ctrl+Z` / `Ctrl+Y`. |

---

## 4. Architectural Breakdown

### Overview

```
my_tools/proms_tester/app.py   (GUI layer — tkinter)
        │
        │  calls
        ▼
xml_fhir_proms_transformer/    (transformer package — installed as a local uv path dep)
  ├── proms_parser.py           parse WPAS XML → PromsMessage
  ├── message_types.py          route OPI / RFI / MPA → MessageType
  ├── proms_transformer.py      assemble FHIR R4B Bundle
  ├── fhir_constants.py         PSOM profile URLs, code systems
  ├── source_systems.py         SYSTEM_ID → health board name / endpoint
  ├── reference_data.py         NHS certification & DHA code lookups, ReferenceDataResolver
  └── mappers/
        ├── mapping_utils.py    UUIDs, Meta, date/name helpers
        ├── message_header_mapper.py
        ├── patient_mapper.py
        ├── care_plan_mapper.py
        ├── task_mapper.py
        └── participant_mappers.py
```

### GUI layer (`app.py`)

`PromsTestApp` is a single `tk.Tk` subclass. It has no business logic of its own —
it is purely a harness around the transformer.

| Component | Class / variable | Purpose |
|---|---|---|
| Header bar | `tk.Frame` (DHCW Navy) | Branding |
| Toolbar | `tk.Frame` (NHS Blue) | Sample load buttons, file open/save, clear |
| Input pane | `self._input_text` (`tk.Text`) | Editable XML — full undo history |
| Output pane | `self._output_text` (`tk.Text`) | Read-only JSON — disabled except during update |
| Transform button | `self._transform_btn` | Triggers `_transform()` |
| Status bar | `self._status_var` (`tk.StringVar`) | Success (green) / failure (red) message |
| Footer | `self._size_var` (`tk.StringVar`) | Byte count + entry count |

The `_transform()` method is the single call site into the transformer:

```python
def _transform(self) -> None:
    xml = self._input_text.get("1.0", tk.END).strip()
    bundle = transform_proms_xml_to_fhir_bundle(xml)  # ← entire pipeline here
    pretty = json.dumps(json.loads(bundle.model_dump_json()), indent=2)
    self._set_output(pretty)
```

`ValueError` (bad XML, unroutable message type, FHIR validation failure) is caught
and shown in the status bar. Any other unexpected exception is also caught so the
GUI never crashes silently.

### Dependency isolation

The tool has its **own isolated `.venv`**, declared in `pyproject.toml`:

```toml
[tool.uv.sources]
proms-fhir-transformer = { path = "../../xml_fhir_proms_transformer" }
```

`uv` installs the transformer as an **editable path dependency** — changes you make
to any file in `xml_fhir_proms_transformer/` take effect immediately the next time
you click **Transform**, with no reinstall step needed. This is what makes
breakpoint debugging in the transformer source work.

### Why tkinter?

- **No extra dependencies** — tkinter ships with every standard Python installation.
- **No separate install step** — `uv sync` only needs to install the transformer and
  its dependencies, not a GUI framework.
- **Runs headlessly in the debugger** — VS Code's `debugpy` attaches to a regular
  Python process; there is no special GUI debugging mode required.

---

## 5. Folder Structure

```
my_tools/
└── proms_tester/
    ├── app.py              GUI entry point — run this
    ├── pyproject.toml      declares the transformer as a local uv path dep
    ├── uv.lock             pinned dependency versions (auto-generated)
    └── .venv/              isolated virtual environment (auto-generated by uv sync)
```

The `.vscode/launch.json` at the **repo root** provides the VS Code debug
configuration. Its `"python"` key points at
`my_tools/proms_tester/.venv/Scripts/python.exe`.

---

## 6. How the Transformer Pipeline Works

When **Transform** is clicked the following sequence runs synchronously on the
main thread (which is why breakpoints work — there is no threading):

```
1. app._transform()
        │
        │  raw XML string
        ▼
2. proms_parser.parse_proms_xml(xml)
        │  defusedxml parses the XML
        │  normalise_key() collapses dialect variants (NHS_NUMBER ≡ nhsNumber ≡ nhs-number)
        │  every leaf element is indexed regardless of nesting depth
        ▼
        PromsMessage  (flat dict-like field view + root_tag)
        │
        ▼
3. message_types.resolve_message_type(message_type, root_tag)
        │  checks MESSAGE_TYPE field, falls back to XML root element
        │  OPI → OUTPATIENT, RFI → REFERRAL, MPA → PATIENT_UPDATE
        │  MPR → ValueError (no mapping defined)
        │  unknown → ValueError
        ▼
        MessageType  (entry order, event coding, practitioner field names)
        │
        ▼
4. proms_transformer.build_fhir_bundle()
        │  allocates UUIDs up front (forward references need them)
        │  branches on PATIENT_UPDATE vs PSOM_REQUEST
        │
        ├─ MPA branch: _build_patient_update_bundle()
        │     MessageHeader + Patient (+ deceasedBoolean)
        │
        └─ OPI / RFI branch: _build_psom_request_bundle()
              MessageHeader
              CarePlan  (pathway, specialty category, activity links)
              Task      (EQ5D5L questionnaire)
              Task      (Data Entry questionnaire)
              Patient   (NHS number + verification, PAS id, name, gender, DOB, postcode)
              Practitioner  (GMC number + name — omitted if no identifier)
              Organization  (ODS code + health board name — omitted if no DHA_CODE)
        │
        ▼
        fhir.resources.R4B.bundle.Bundle  (fully validated FHIR R4B model)
        │
        ▼
5. bundle.model_dump_json()  →  JSON string  →  pretty-printed  →  output pane
```

### WPAS fields used by the pipeline

| WPAS Field | Used by |
|---|---|
| `SYSTEM_ID` | Source system lookup (health board name, endpoint, PAS identifier system) |
| `DHA_CODE` | Organisation name (`dha_code_name()`), ODS code |
| `UNIQUE_ID` | `CarePlan.identifier.value` (episode identifier) |
| `NHS_NUMBER` | `Patient.identifier[0]` |
| `NHS_CERTIFICATION` | NHS number verification status extension (`nhs_certification_display()`) |
| `UNIT_NUMBER` | `Patient.identifier[1]` (PAS / unit number) |
| `SURNAME`, `FORENAME` | `Patient.name`, `MessageHeader.focus[0].display` |
| `SEX` | `Patient.gender` (via `StaticReferenceDataResolver`) |
| `BIRTHDATE` | `Patient.birthDate` |
| `POSTCODE` | `Patient.address[0].postalCode` |
| `DEATHDATE` | `Patient.deceasedBoolean` (MPA only; length > 2 → true) |
| `PREFERRED_LANGUAGE` | `Patient.communication` (omitted — no Core Reference Data service) |
| `SPEC`, `SPEC_NAME` | `CarePlan.category`, `MessageHeader.focus[0].display` |
| `CONS_NAME` | `Practitioner.name` (OPI), `MessageHeader.responsible.display` |
| `CONS_GMC` | `Practitioner.identifier` (OPI) |
| `REFERRING_GP` | `Practitioner.identifier` + `MessageHeader.responsible.display` (RFI) |
| `UPI_EVENT`, `UPI_EVENT_DESC` | `Task.reasonCode` (trigger event type) |
| `UPI_EVENT_DATE` | `Task.input[0]` (EQ5D5L task only) |

---

## 7. Updating the Tool

**If you change transformer source files** (mappers, parser, constants, etc.),
no reinstall is needed — the path dep is live. Just click Transform again.

**If you add new Python dependencies** to `xml_fhir_proms_transformer/pyproject.toml`,
re-run from this folder:

```powershell
uv sync
```

**If you want to update this tool's own dependencies:**

```powershell
uv lock --upgrade
uv sync
```
