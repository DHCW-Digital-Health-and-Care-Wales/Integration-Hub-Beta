# Integration Hub Tester — Developer Tool

A local developer GUI for testing and debugging **all Integration Hub services**
from a single tabbed window, without running any Azure infrastructure, Service Bus
connections, or MLLP ports.

> **Not tracked by git.** This tool lives in `my_tools/` which is listed in the
> repo-root `.gitignore`. It will never appear in a commit or pull request.

---

## Contents

1. [Quick Start](#1-quick-start)
2. [Running with the VS Code Debugger (breakpoints)](#2-running-with-the-vs-code-debugger-breakpoints)
3. [Service Tabs — What Each One Does](#3-service-tabs--what-each-one-does)
4. [GUI Features](#4-gui-features)
5. [Architectural Breakdown](#5-architectural-breakdown)
6. [Folder Structure](#6-folder-structure)
7. [How Each Service Is Invoked](#7-how-each-service-is-invoked)
8. [Adding a New Service Tab](#8-adding-a-new-service-tab)
9. [Updating the Tool](#9-updating-the-tool)

---

## 1. Quick Start

### Prerequisites

- Python 3.13+
- [`uv`](https://docs.astral.sh/uv/) installed
- The repo cloned locally with all transformer directories present

### Install & run

```powershell
cd my_tools\integration_hub_tester
uv sync          # creates .venv and installs all 5 services as live path deps (first time only)
uv run python app.py
```

The GUI opens immediately — no Azure credentials, no Service Bus connection,
no config file edits required.

---

## 2. Running with the VS Code Debugger (breakpoints)

A **VS Code launch configuration** has been added at `.vscode/launch.json` in the
repo root. It targets this tool's isolated `.venv` and sets `"justMyCode": false`
so the debugger steps into all service source code, not just `app.py`.

### Steps

1. Open the repo root in VS Code (`code .`).
2. Open **Run and Debug** — `Ctrl + Shift + D`.
3. Select **"Integration Hub Tester GUI"** from the dropdown.
4. Press **F5**.
5. Set breakpoints in the service source files listed below and click the action
   button on the relevant tab. VS Code pauses at your breakpoint.

### Where to set breakpoints per service

| Tab | Useful breakpoint locations |
|---|---|
| **PHW Transformer** | `transformers/hl7_phw_transformer/phw_transformer.py` → `transform_message()` · `mappers/msh_mapper.py` · `mappers/pid_mapper.py` |
| **Chemo Transformer** | `transformers/hl7_chemo_transformer/chemocare_transformer.py` → `transform_chemocare_message()` · any mapper in `mappers/` |
| **PIMS Transformer** | `transformers/hl7_pims_transformer/pims_transformer.py` → `transform_pims_message()` · `mappers/mrg_mapper.py` (for A40 merges) |
| **PROMS Transformer** | `transformers/xml_fhir_proms_transformer/proms_transformer.py` → `build_fhir_bundle()` · any mapper in `mappers/` · `proms_parser.py` |
| **HL7 Server** | `hl7_server/hl7_validator.py` → `validate()` · `hl7_server/hl7_ack_builder.py` → `build_ack()` |
| **HL7 Sender** | `services/hl7_sender_plugin.py` → `run()` to inspect the MLLP byte frame before it is displayed |

Use **F10** to step over, **F11** to step into, and the Watch / Variables panels to
inspect intermediate values at any point in the pipeline.

---

## 3. Service Tabs — What Each One Does

### PHW Transformer

| | |
|---|---|
| **Input** | HL7v2 ER7 — ADT A28 (new patient) or A31 (patient update) from Public Health Wales |
| **Output** | Transformed HL7v2 v2.5 ER7 — remapped MSH, EVN, PID, PD1 segments |
| **Underlying code** | `transformers/hl7_phw_transformer/hl7_phw_transformer/phw_transformer.py` · `PhwTransformer.transform_message()` |
| **Samples** | A28 (PHW fixture), A31 (Southwest) |

### Chemo Transformer

| | |
|---|---|
| **Input** | HL7v2 ER7 — ADT A28 / A31 from ChemoCare |
| **Output** | Transformed HL7v2 v2.5 ER7 — remapped MSH, EVN, PID, PD1, NK1 segments |
| **Underlying code** | `transformers/hl7_chemo_transformer/hl7_chemo_transformer/chemocare_transformer.py` · `transform_chemocare_message()` |
| **Samples** | A31 Southwest, A28 Southwest, A28 Velindre |

### PIMS Transformer

| | |
|---|---|
| **Input** | HL7v2 ER7 — ADT A04 (new patient), A08 (patient update), A40 (patient merge) from PIMS |
| **Output** | Transformed HL7v2 v2.5 ER7 — remapped MSH, EVN, PID, PD1, PV1, MRG segments |
| **Underlying code** | `transformers/hl7_pims_transformer/hl7_pims_transformer/pims_transformer.py` · `transform_pims_message()` |
| **Notes** | A40 messages in the ADT_A39 grouped structure are automatically re-parsed as flat before mapping |
| **Samples** | A04 (New patient), A08 (Patient update), A40 (Merge) |

### PROMS Transformer

| | |
|---|---|
| **Input** | WPAS XML — OPI (Outpatient), RFI (Referral), or MPA (Patient Update) |
| **Output** | FHIR R4B JSON message Bundle (PSOM — Patient Standard Outcome Measures) |
| **Underlying code** | `transformers/xml_fhir_proms_transformer/xml_fhir_proms_transformer/proms_transformer.py` · `transform_proms_xml_to_fhir_bundle()` |
| **Samples** | OPI (Outpatient), RFI (Referral), MPA (Patient Update) |

### HL7 Server

| | |
|---|---|
| **Input** | HL7v2 ER7 — any ADT message as it would arrive at the MLLP port |
| **Output** | Parsed message summary + validation result + ACK ER7 preview |
| **Underlying code** | `hl7_server/hl7_server/hl7_validator.py` · `HL7Validator.validate()` and `hl7_server/hl7_server/hl7_ack_builder.py` · `HL7AckBuilder.build_ack()` |
| **Notes** | No MLLP port is opened. Uses the same validator and ACK builder the real server uses. Validation runs without flow-specific rules (generic check). |
| **Samples** | Valid A28 (v2.5), Valid A31 (v2.5), Wrong version (A31 v2.3) |

### HL7 Sender

| | |
|---|---|
| **Input** | HL7v2 ER7 — as it would arrive from the Service Bus queue |
| **Output** | MLLP byte frame breakdown + annotated segment listing |
| **Underlying code** | Implemented directly in `services/hl7_sender_plugin.py` — no import of the sender service needed (MLLP framing is three bytes: `0x0B` + payload + `0x1C 0x0D`) |
| **Notes** | No TCP connection is made. Covers both `hl7_sender` (queue) and `hl7_subscription_sender` (subscription) since they produce identical MLLP frames. |
| **Samples** | ADT A01 (Inpatient admit), ADT A28 (New patient) |

---

## 4. GUI Features

| Feature | Detail |
|---|---|
| **Tabbed notebook** | One tab per service. Tabs are styled with DHCW brand colours. |
| **Load sample buttons** | Each tab has buttons to pre-load named sample messages. Edit the XML or ER7 inline to test specific field variations. |
| **Open file** | Load any `.hl7`, `.xml`, `.json`, or `.txt` file from disk. |
| **Save output** | Saves the current output pane to a file. Extension is inferred (`.json` for FHIR output, `.txt` for everything else). |
| **Clear** | Empties both panes. |
| **Action button** | Runs the service logic. Text varies per tab: `▶ Transform`, `🔍 Validate + Preview ACK`, `📡 Preview MLLP Frame`. |
| **Ctrl+Return** | Keyboard shortcut to trigger the active tab's action button. |
| **Status bar** | Per-tab `✓` (green) on success with a brief summary, or `✗` (red) with the error message on failure. |
| **Character count** | Shows output size in the bottom-right of each tab after a successful run. |
| **Undo / redo** | Standard `Ctrl+Z` / `Ctrl+Y` in every input pane. |

---

## 5. Architectural Breakdown

### Overview

```
my_tools/integration_hub_tester/
│
├── app.py                         GUI layer — tk.Tk + ttk.Notebook
│     └── ServicePage              reusable tab widget (one per plugin)
│
└── services/
      ├── base.py                  ServicePlugin ABC  (run() → tuple[str, str])
      ├── phw_plugin.py            PhwPlugin
      ├── chemo_plugin.py          ChemoPlugin
      ├── pims_plugin.py           PimsPlugin
      ├── proms_plugin.py          PromsPlugin
      ├── hl7_server_plugin.py     Hl7ServerPlugin
      └── hl7_sender_plugin.py     Hl7SenderPlugin
                │
                │  each plugin imports from a live path dep:
                ▼
transformers/hl7_phw_transformer/   installed as path dep in .venv
transformers/hl7_chemo_transformer/    installed as path dep in .venv
transformers/hl7_pims_transformer/     installed as path dep in .venv
transformers/xml_fhir_proms_transformer/ installed as path dep in .venv
hl7_server/                        installed as path dep in .venv
```

### The `ServicePlugin` contract

Every tab is backed by a single class that inherits from `ServicePlugin`:

```python
class ServicePlugin(ABC):
    tab_label: str          # text on the notebook tab
    description: str        # one-line banner at the top of the tab
    input_label: str        # label above the input pane
    output_label: str       # label above the output pane
    button_label: str       # action button text
    samples: dict[str, str] # named samples loaded by toolbar buttons

    @abstractmethod
    def run(self, input_text: str) -> tuple[str, str]:
        """Return (output_text, status_summary) or raise an exception."""
```

The `ServicePage` widget is **entirely generic** — it knows nothing about HL7, FHIR
or MLLP. It calls `plugin.run(input)`, displays the output, and handles errors.
Adding a new service tab requires zero changes to `app.py` or `ServicePage`.

### How the GUI layer works

`IntegrationHubTesterApp` creates one `ServicePage` per plugin and adds them to a
`ttk.Notebook`. The `PLUGINS` list at the top of `app.py` controls tab order:

```python
PLUGINS: list[ServicePlugin] = [
    PhwPlugin(),
    ChemoPlugin(),
    PimsPlugin(),
    PromsPlugin(),
    Hl7ServerPlugin(),
    Hl7SenderPlugin(),
]
```

`ServicePage._run()` is the single call site into the service logic:

```python
def _run(self) -> None:
    output, summary = self._plugin.run(input_text)  # ← entire pipeline here
    self._set_output(output)
    self._set_status(summary, ok=summary.startswith("✓"))
```

`ValueError` (bad HL7, unroutable message type, validation failure) is caught and
shown in red. Any other exception is also caught so the GUI never crashes silently.
All code runs synchronously on the main thread — this is why breakpoints work.

### Dependency isolation

The tool has its **own isolated `.venv`**, declared in `pyproject.toml`:

```toml
[tool.uv.sources]
hl7-phw-transformer   = { path = "../../transformers/hl7_phw_transformer" }
hl7-chemo-transformer = { path = "../../transformers/hl7_chemo_transformer" }
hl7-pims-transformer  = { path = "../../transformers/hl7_pims_transformer" }
proms-fhir-transformer = { path = "../../transformers/xml_fhir_proms_transformer" }
hl7-server            = { path = "../../hl7_server" }
```

All five are installed as **live path dependencies** — changes you make to any
source file in those directories take effect the next time you click the action
button, with no reinstall step needed. This is what makes breakpoint debugging in
the service source files work.

### Bypassing `BaseTransformer.__init__`

The three HL7v2 transformer classes (`PhwTransformer`, `ChemocareTransformer`,
`PimsTransformer`) inherit from `BaseTransformer`, whose `__init__` reads
`config.ini` and tries to connect to Azure Service Bus. To avoid this the plugins
use one of two approaches:

| Service | Approach |
|---|---|
| **Chemo / PIMS** | Use the module-level standalone function (`transform_chemocare_message`, `transform_pims_message`) directly — no class instantiation at all |
| **PHW** | Use `object.__new__(PhwTransformer)` to allocate the instance without calling `__init__`, then set the two instance attributes the method needs (`_current_datetime_transformation`, `_current_dod_transformation`) |

The PROMS transformer has a module-level `transform_proms_xml_to_fhir_bundle()`
function and the HL7 Server's `HL7Validator` and `HL7AckBuilder` have no
infrastructure dependencies, so both are instantiated normally.

---

## 6. Folder Structure

```
my_tools/
└── integration_hub_tester/
    ├── app.py              Main window — run this
    ├── pyproject.toml      Lists all 5 services as live path deps
    ├── uv.lock             Pinned dependency versions (auto-generated)
    ├── .venv/              Isolated virtual environment (auto-generated by uv sync)
    └── services/
          ├── __init__.py
          ├── base.py
          ├── phw_plugin.py
          ├── chemo_plugin.py
          ├── pims_plugin.py
          ├── proms_plugin.py
          ├── hl7_server_plugin.py
          └── hl7_sender_plugin.py
```

The `.vscode/launch.json` at the **repo root** provides the VS Code debug
configuration. Its `"python"` key points at
`my_tools/integration_hub_tester/.venv/Scripts/python.exe`.

---

## 7. How Each Service Is Invoked

The pipeline for each tab when the action button is clicked:

### HL7v2 Transformers (PHW / Chemo / PIMS)

```
1. plugin.run(er7_string)
        │
        │  replace \n → \r  (ER7 uses CR as segment separator)
        ▼
2. hl7apy.parser.parse_message(er7, find_groups=False)
        │  parses all segments into a flat hl7apy.Message object
        ▼
3. transform_*(msg)  or  transformer.transform_message(msg)
        │  remaps MSH, EVN, PID, PD1, PV1, NK1, MRG into a new Message(version="2.5")
        ▼
4. result.to_er7()
        │  serialises back to ER7 string  (\r → \n for display)
        ▼
5. output pane  +  status summary
```

### PROMS Transformer

```
1. plugin.run(wpas_xml_string)
        │
        ▼
2. parse_proms_xml(xml)      ← defusedxml, dialect-tolerant, depth-insensitive
        │
        ▼  PromsMessage (flat field view + root_tag)
        │
        ▼
3. resolve_message_type(message_type, root_tag)
        │  OPI → OUTPATIENT  |  RFI → REFERRAL  |  MPA → PATIENT_UPDATE
        ▼
4. build_fhir_bundle(message)
        │  allocates UUIDs, assembles R4B resources, positional entry order
        ▼
5. bundle.model_dump_json()  →  pretty-printed JSON  →  output pane
```

### HL7 Server

```
1. plugin.run(er7_string)
        │
        ▼
2. parse_message(er7, find_groups=False)
        │
        ▼
3. Produce message summary (MSH fields, segment list)
        │
        ▼
4. HL7Validator().validate(msg)
        │  checks HL7 version, sending app, generic rules
        │  raises ValidationException on failure
        ▼
5. HL7AckBuilder().build_ack(control_id, msg)
        │  builds ACK message with MSA AA, mirroring sender/receiver from MSH
        ▼
6. output pane  (summary + validation result + ACK ER7)
```

### HL7 Sender (MLLP frame preview)

```
1. plugin.run(er7_string)
        │
        ▼
2. parse_message(er7, find_groups=False)   ← validate the HL7 is parseable
        │
        ▼
3. Build MLLP frame:
        0x0B  +  er7.encode("utf-8")  +  0x1C  +  0x0D
        │
        ▼
4. output pane  (message summary + byte breakdown + annotated segment listing + hex of control bytes)
```

---

## 8. Adding a New Service Tab

1. Create `services/my_new_plugin.py`:

```python
from services.base import ServicePlugin

class MyNewPlugin(ServicePlugin):
    tab_label = "My Service"
    description = "One-line description of what this service does"
    input_label = "Input  (describe format)"
    output_label = "Output  (describe format)"
    button_label = "▶  Run"
    samples = {
        "Sample A": "...sample content...",
    }

    def __init__(self) -> None:
        pass

    def run(self, input_text: str) -> tuple[str, str]:
        # Import your service here (lazy import avoids startup cost).
        from my_service.my_transformer import do_transform

        result = do_transform(input_text.strip())
        return result, "✓  Transformation complete"
```

2. Register it in `app.py`:

```python
from services.my_new_plugin import MyNewPlugin

PLUGINS: list[ServicePlugin] = [
    PhwPlugin(),
    ...
    MyNewPlugin(),   # ← add here
]
```

3. Add the service as a path dep in `pyproject.toml` and run `uv sync`.

That's it — `ServicePage` handles all the UI automatically.

---

## 9. Updating the Tool

**If you change transformer source files**, no reinstall is needed — the path
deps are live. Just click the action button again.

**If you add new Python dependencies** to any service's `pyproject.toml`,
re-run from this folder:

```powershell
uv sync
```

**To upgrade all pinned versions:**

```powershell
uv lock --upgrade
uv sync
```
