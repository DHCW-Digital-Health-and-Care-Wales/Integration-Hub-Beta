# Component Tester — Developer Tool

A local developer GUI for testing and debugging **all Integration Hub services**
from a single tabbed window, without running any Azure infrastructure, Service Bus
connections, or MLLP ports.

> **Not tracked by build/deploy pipelines.** This tool lives in `dev_tools/` alongside
> other internal developer utilities — it is not part of any container image or
> ADO pipeline; it's a local-only dev aid.

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
- The repo cloned locally with all transformer/server/sender directories present

### Install & run

```powershell
cd dev_tools\integration_hub_tester
uv sync          # creates .venv and installs all path deps (first time only, or after a pyproject.toml change)
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
3. Select **"Component Tester GUI"** from the dropdown.
4. Press **F5**.
5. Set breakpoints in the service source files listed below and click the action
   button on the relevant tab. VS Code pauses at your breakpoint.

### Where to set breakpoints per service

| Tab | Useful breakpoint locations |
|---|---|
| **PHW Transformer** | `transformers/hl7_phw_transformer/phw_transformer.py` → `transform_message()` · `mappers/msh_mapper.py` · `mappers/pid_mapper.py` |
| **Chemo Transformer** | `transformers/hl7_chemo_transformer/chemocare_transformer.py` → `transform_chemocare_message()` · any mapper in `mappers/` |
| **PIMS Transformer** | `transformers/hl7_pims_transformer/pims_transformer.py` → `transform_pims_message()` · `mappers/mrg_mapper.py` (for A40 merges) |
| **Core Reference Transformer** | `transformers/hl7_core_reference_transformer/mappers/pid_reference_mapper.py` → `apply_core_reference_mapping()` |
| **PROMS Transformer** | `transformers/xml_fhir_proms_transformer/proms_transformer.py` → `transform_proms_xml_to_fhir_bundle()` · any mapper in `mappers/` |
| **HL7 Server** | `servers/hl7_server/hl7_server/hl7_validator.py` → `validate()` · `hl7_ack_builder.py` → `build_ack()`/`build_nack()`/`build_generic_nack()` · `error_handler.py` → `ErrorHandler.reply()` |
| **HL7 Sender** | `services/hl7_sender_plugin.py` → `run()` to inspect the MLLP byte frame before it is displayed |
| **HL7 Sender ACK** | `senders/hl7_sender/hl7_sender/ack_processor.py` → `get_ack_result()` |
| **REST Server (HL7)** | `servers/rest_server/rest_server/hl7/hl7_message_processor.py` → `Hl7MessageProcessor.process()` |
| **HL7 SOAP Server** | `servers/hl7_soap_server/hl7_soap_server/soap_processor.py` → `SoapMessageProcessor.process()` |
| **SOAP Sender / SOAP Sub Sender** | `services/soap_sender_plugin.py` / `services/soap_subscription_sender_plugin.py` → `run()` |

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

### Core Reference Transformer

| | |
|---|---|
| **Input** | RISP-style ADT ER7 — A28 / A31 / A40 (other trigger types pass through unchanged) |
| **Output** | Same message with PID Sex / Title / Language / Marital Status / Religion / Ethnicity translated |
| **Underlying code** | `transformers/hl7_core_reference_transformer/hl7_core_reference_transformer/mappers/pid_reference_mapper.py` · `apply_core_reference_mapping()` |
| **Notes** | ⚠ Uses a small **demo WRDS fixture** baked into the plugin (`services/core_reference_plugin.py`) instead of a live WRDS SOAP endpoint — `ToCode` values shown are demo data only, not real reference-data lookups. `CoreReferenceTransformer` itself is not instantiated (it needs Service Bus config); the standalone mapping function is called directly instead. |
| **Samples** | A28 (all 6 fields populated), A31 (no coded fields), A04 (out of scope — passes through) |

### PROMS Transformer

| | |
|---|---|
| **Input** | WPAS XML (`PromsEventRequest`) |
| **Output** | FHIR R4B JSON message Bundle |
| **Underlying code** | `transformers/xml_fhir_proms_transformer/xml_fhir_proms_transformer/proms_transformer.py` · `transform_proms_xml_to_fhir_bundle()` |
| **Supported eventCodes** | `REFERRAL` · `SURGERY` (legacy Procedure) / `SURGERY-PERF` (Surgery Performed) / `SURGERY-DN` (Discharge) · `PREOP` (legacy Appointment) / `PREOP-VIS` (Outpatient Visit) / `PREOP-AR` (Appointment Reschedule) · `INPATIENT` · `CANCELLED` · `PREREAD` |
| **Notes** | ⚠ `-PERF`/`-DN`/`-VIS`/`-AR` suffixed eventCodes are **TEMP placeholder values** (no confirmed WPAS codes yet for these scenarios) — see `transformers/xml_fhir_proms_transformer/README.md` for full detail and the `# TEMP` markers in the transformer source |
| **Samples** | One per eventCode listed above (10 total) |

### HL7 Server

| | |
|---|---|
| **Input** | HL7v2 ER7 — any ADT message, or an unparsable string, as it would arrive at the MLLP port |
| **Output** | Parsed message summary + validation result + ACK (AA) or NACK (AR/AE) ER7 preview |
| **Underlying code** | `servers/hl7_server/hl7_server/hl7_validator.py` · `HL7Validator.validate()` · `hl7_ack_builder.py` · `HL7AckBuilder.build_ack()`/`build_nack()`/`build_generic_nack()` · `error_handler.py` · `ErrorHandler` (real classification/NACK-building logic) |
| **Notes** | No MLLP port is opened. `EventLogger` is instantiated normally — with no `APPLICATIONINSIGHTS_CONNECTION_STRING` set locally it safely falls back to standard logging (no network calls). Validation runs without flow-specific rules (generic check, `hl7_version="2.5"`). |
| **Samples** | Valid A28 (v2.5) → AA · Valid A31 (v2.5) → AA · Wrong version (A31 v2.3) → AR NACK · Unparsable → AE NACK (generic) |

### HL7 Sender

| | |
|---|---|
| **Input** | HL7v2 ER7 — as it would arrive from the Service Bus queue |
| **Output** | MLLP byte frame breakdown + annotated segment listing |
| **Underlying code** | Implemented directly in `services/hl7_sender_plugin.py` — no import of the sender service needed (MLLP framing is three bytes: `0x0B` + payload + `0x1C 0x0D`) |
| **Notes** | No TCP connection is made. Covers both `hl7_sender` (queue) and `hl7_subscription_sender` (subscription) since they produce identical MLLP frames. |
| **Samples** | ADT A01 (Inpatient admit), ADT A28 (New patient) |

### HL7 Sender ACK

| | |
|---|---|
| **Input** | A simulated ACK/NACK response, as it would be received back over MLLP |
| **Output** | Classification: `SUCCESS` (AA/CA) · `AE` (recoverable, retried) · `AR` (non-recoverable, dead-lettered) · `INVALID` (malformed/missing MSA) |
| **Underlying code** | `senders/hl7_sender/hl7_sender/ack_processor.py` · `get_ack_result()` — a pure function, called unmodified |
| **Notes** | Also covers `hl7_subscription_sender`, which uses the same classification logic. |
| **Samples** | AA — success, AE — recoverable, AR — non-recoverable, Malformed response |

### REST Server (HL7)

| | |
|---|---|
| **Input** | HL7v2 ER7 (shown as the `messageContent` value the real API expects as JSON) |
| **Output** | HTTP status + ACK (201) / NACK (422 validation, 500 parse) body |
| **Underlying code** | `servers/rest_server/rest_server/hl7/hl7_message_processor.py` · `Hl7MessageProcessor.process()` — the real `hl7` pipeline, no flow (`HL7_VALIDATION_FLOW` unset) |
| **Notes** | ⚠ Supersedes the retired `hl7_rest_server` service (see `servers/rest_server/README.md`) — no separate tab is provided for it. Only the outbound I/O boundary (Service Bus sender, message store) is stubbed with no-op mocks; validation/ACK/NACK logic is unmodified production code. The `generic` pipeline and `mpi`/`risp` flow-specific rules are not covered by this tab. |
| **Samples** | Valid A28 (v2.5) → 201 ACK, Malformed → 500 NACK |

### HL7 SOAP Server

| | |
|---|---|
| **Input** | HL7v2 ER7 (converted to HL7 v2.xml and wrapped in a SOAP envelope by the plugin) |
| **Output** | HTTP status + SOAP `AckResponse` (200) / SOAP `Fault` (400/403/500) |
| **Underlying code** | `servers/hl7_soap_server/hl7_soap_server/soap_processor.py` · `SoapMessageProcessor.process()` — real SOAP unwrap, allowed-structure check, XSD schema validation, assigning-authority check |
| **Notes** | Fixed for this preview: `schema_group="phw"`, `allowed_hl7_structures=["ADT_A05", "ADT_A39"]`, `allowed_assigning_authorities=["328"]`. Only the outbound I/O boundary is stubbed with no-op mocks (the same pattern the service's own tests use). |
| **Samples** | Valid ADT_A05 (authority 328) → 200, Malformed SOAP request → 400, Unknown assigning authority (999) → 403 |

### SOAP Sender / SOAP Sub Sender

| | |
|---|---|
| **Input** | HL7v2 ER7 |
| **Output** | The SOAP envelope built, and (if `http_mock_receiver` is running) the live HTTP response from it |
| **Underlying code** | `services/soap_sender_plugin.py` / `services/soap_subscription_sender_plugin.py` |
| **Notes** | Makes a real HTTP POST to the mock receiver (default `http://localhost:8080/soap`, override with `SOAP_MOCK_URL`) if it is running (see the Mock Receiver bar below); otherwise falls back to an offline envelope preview. The two tabs are functionally identical — they exist separately to confirm both senders produce the same envelope. |
| **Samples** | ADT A01, ADT A28, a message crafted to trigger the mock receiver's fault path |

### Mock Receiver bar (not a tab)

A persistent toolbar in the header (`services/mock_receiver_manager.py`) starts/stops
`hl7_mock_receiver` (MLLP) or `http_mock_receiver` (SOAP) in a separate visible console window, so
the **SOAP Sender** tabs can be tested end-to-end against a live receiver. Stopped automatically
when the tester window is closed.

---

## 4. GUI Features

| Feature | Detail |
|---|---|
| **Sidebar + underline tabs** | A left-hand sidebar lists service categories (`🔧 Transformers`, `🖥 Servers`, `📤 Senders`) — click to switch. The content area shows the selected category's services as an underline-style tab strip (similar to desktop tools like Podman Desktop) rather than a boxed notebook; click a service name to switch pages. |
| **Light/Dark theme toggle** | Button in the top-right of the header (`🌙 Dark mode` / `☀ Light mode`). Rebuilds the whole widget tree with the new palette (see `THEMES` in `app.py`) and restores the previously-selected category/service. Unsaved input/output text in each tab is reset by the rebuild. |
| **Mock Receiver bar** | Persistent toolbar in the header (row 2, right-aligned) to start/stop the MLLP or SOAP mock receiver in a separate console window — see above. |
| **Load sample dropdown** | Each tab has a dropdown (not one button per sample) to pre-load named sample messages — selecting a value loads it immediately, or use the "Load" link to reload the current selection. Edit the XML or ER7 inline to test specific field variations. |
| **Open file** | Load any `.hl7`, `.xml`, `.json`, or `.txt` file from disk. |
| **Save output** | Saves the current output pane to a file. Extension is inferred (`.json` for FHIR output, `.txt` for everything else). |
| **Clear** | Empties both panes. |
| **Action button** | Runs the service logic. Text varies per tab: `▶ Transform`, `🔍 Validate + Preview ACK/NACK`, `📡 Preview MLLP Frame`, `🔍 Classify Response`. This is the only solid-coloured button on a tab — Load/Open/Save/Clear are flat "link-style" buttons to keep the toolbar visually minimal. |
| **Ctrl+Return** | Keyboard shortcut to trigger the active tab's action button. |
| **Status bar** | Per-tab `✓` (green) on success with a brief summary, or `✗` (red) with the error message on failure. |
| **Character count** | Shows output size in the bottom-right of each tab after a successful run. |
| **Undo / redo** | Standard `Ctrl+Z` / `Ctrl+Y` in every input pane. |

---

## 5. Architectural Breakdown

### Overview

```
dev_tools/integration_hub_tester/
│
├── app.py                              GUI layer — tk.Tk + sidebar/underline tabs
│     └── ServicePage                   reusable tab widget (one per plugin)
│
└── services/
      ├── base.py                       ServicePlugin ABC  (run() → tuple[str, str])
      ├── phw_plugin.py                 PhwPlugin
      ├── chemo_plugin.py               ChemoPlugin
      ├── pims_plugin.py                PimsPlugin
      ├── core_reference_plugin.py      CoreReferencePlugin
      ├── proms_plugin.py               PromsPlugin
      ├── hl7_server_plugin.py          Hl7ServerPlugin
      ├── hl7_sender_plugin.py          Hl7SenderPlugin
      ├── hl7_sender_ack_plugin.py      Hl7SenderAckPlugin
      ├── rest_server_plugin.py         RestServerPlugin
      ├── hl7_soap_server_plugin.py     HL7SoapServerPlugin
      ├── soap_sender_plugin.py         SoapSenderPlugin
      ├── soap_subscription_sender_plugin.py  SoapSubscriptionSenderPlugin
      └── mock_receiver_manager.py      MockReceiverManager  (toolbar, not a plugin)
                │
                │  each plugin imports from a live path dep:
                ▼
transformers/hl7_phw_transformer/            installed as path dep in .venv
transformers/hl7_chemo_transformer/          installed as path dep in .venv
transformers/hl7_pims_transformer/           installed as path dep in .venv
transformers/hl7_core_reference_transformer/ installed as path dep in .venv
transformers/xml_fhir_proms_transformer/     installed as path dep in .venv
servers/hl7_server/                          installed as path dep in .venv
servers/rest_server/                         installed as path dep in .venv
servers/hl7_soap_server/                     installed as path dep in .venv
senders/hl7_sender/                          installed as path dep in .venv
shared_libs/wrds_service/                    installed as path dep in .venv
```

### The `ServicePlugin` contract

Every tab is backed by a single class that inherits from `ServicePlugin`:

```python
class ServicePlugin(ABC):
    tab_label: str          # text on the underline-style service tab
    description: str        # one-line banner at the top of the tab
    input_label: str        # label above the input pane
    output_label: str       # label above the output pane
    button_label: str       # action button text
    samples: dict[str, str] # named samples, selected via a dropdown + Load button

    @abstractmethod
    def run(self, input_text: str) -> tuple[str, str]:
        """Return (output_text, status_summary) or raise an exception."""
```

The `ServicePage` widget is **entirely generic** — it knows nothing about HL7, FHIR
or MLLP. It calls `plugin.run(input)`, displays the output, and handles errors.
Adding a new service tab requires zero changes to `app.py` or `ServicePage`.

### How the GUI layer works

`IntegrationHubTesterApp` creates one `ServicePage` per plugin. Services are
grouped into categories — **🔧 Transformers**, **🖥 Servers**, **📤 Senders** —
listed as clickable entries in a left-hand sidebar (`tk.Label` widgets, not a
`ttk.Notebook`). Clicking a category raises its content container, which shows
that category's services as an underline-style tab strip (plain `tk.Label` +
a thin `tk.Frame` "underline" bar per service, coloured when active) with the
matching `ServicePage` stacked below via `grid`/`tkraise`. This mirrors the
layout of common desktop dev tools (e.g. Podman Desktop) and keeps the sidebar
a fixed, small width regardless of how many individual services get added over
time. `PLUGIN_CATEGORIES` at the top of `app.py` controls both the grouping
and the tab order within each group:

```python
PLUGIN_CATEGORIES: list[tuple[str, list[ServicePlugin]]] = [
    ("🔧 Transformers", [phw_plugin, chemo_plugin, pims_plugin, core_reference_plugin, proms_plugin]),
    ("🖥 Servers", [hl7_server_plugin, rest_server_plugin, hl7_soap_server_plugin]),
    ("📤 Senders", [hl7_sender_plugin, hl7_sender_ack_plugin, soap_sender_plugin, soap_subscription_sender_plugin]),
]
```

The `PLUGINS` flat list above it still lists every plugin instance once (handy
for smoke-testing that every plugin imports/instantiates cleanly) but no longer
drives the layout directly.

Each tab's sample toolbar is a `ttk.Combobox` dropdown (not one button per
sample) so it stays a fixed width too — some tabs (e.g. PROMS) already have 9+
samples, and a button-per-sample row would overflow the window. Selecting a
value loads it immediately; there's also an explicit "Load" button for
re-loading the currently-selected value.

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
hl7-phw-transformer             = { path = "../../transformers/hl7_phw_transformer" }
hl7-chemo-transformer           = { path = "../../transformers/hl7_chemo_transformer" }
hl7-pims-transformer            = { path = "../../transformers/hl7_pims_transformer" }
hl7-core-reference-transformer  = { path = "../../transformers/hl7_core_reference_transformer" }
proms-fhir-transformer          = { path = "../../transformers/xml_fhir_proms_transformer" }
hl7-server                      = { path = "../../servers/hl7_server" }
rest-server                     = { path = "../../servers/rest_server" }
hl7-soap-server                 = { path = "../../servers/hl7_soap_server" }
hl7-sender                      = { path = "../../senders/hl7_sender" }
wrds-service                    = { path = "../../shared_libs/wrds_service" }
```

All are installed as **live path dependencies** — changes you make to any source
file in those directories take effect the next time you click the action button,
with no reinstall step needed (except after editing a `pyproject.toml`, which
needs `uv sync`). This is what makes breakpoint debugging in the service source
files work.

### Bypassing infrastructure dependencies (`BaseTransformer`, Service Bus, WRDS)

Several service classes have constructors that read config and/or connect to
Azure Service Bus (or, for Core Reference, call a live WRDS SOAP endpoint), which
aren't available locally. Each plugin works around this differently:

| Service | Approach |
|---|---|
| **Chemo / PIMS / Core Reference** | Use the module-level standalone function (`transform_chemocare_message`, `transform_pims_message`, `apply_core_reference_mapping`) directly — no class instantiation at all |
| **PHW** | Use `object.__new__(PhwTransformer)` to allocate the instance without calling `__init__`, then set the two instance attributes the method needs |
| **PROMS** | Module-level `transform_proms_xml_to_fhir_bundle()` function — no class involved |
| **HL7 Server** | `HL7Validator`, `HL7AckBuilder`, and `ErrorHandler` have no infrastructure dependencies (`ErrorHandler` needs an `EventLogger`, which is instantiated normally — see notes above) |
| **HL7 Sender ACK** | `get_ack_result()` is a pure function — no class involved |
| **REST Server (HL7) / HL7 SOAP Server** | The real `Hl7MessageProcessor`/`SoapMessageProcessor` classes are instantiated, but with `unittest.mock.MagicMock()` standing in for the Service Bus sender and message store client (the only genuine outbound I/O) — the same pattern each service's own test suite uses |
| **Core Reference's WRDS lookup** | `WRDSService` is instantiated with `fixture_file_path` pointing at a small demo fixture file the plugin builds at runtime, instead of a live endpoint URL — see the Core Reference Transformer notes above |

---

## 6. Folder Structure

```
dev_tools/
└── integration_hub_tester/
    ├── app.py              Main window — run this
    ├── pyproject.toml      Lists all services as live path deps
    ├── uv.lock             Pinned dependency versions (auto-generated)
    ├── .venv/              Isolated virtual environment (auto-generated by uv sync)
    └── services/
          ├── __init__.py
          ├── base.py
          ├── phw_plugin.py
          ├── chemo_plugin.py
          ├── pims_plugin.py
          ├── core_reference_plugin.py
          ├── proms_plugin.py
          ├── hl7_server_plugin.py
          ├── hl7_sender_plugin.py
          ├── hl7_sender_ack_plugin.py
          ├── rest_server_plugin.py
          ├── hl7_soap_server_plugin.py
          ├── soap_sender_plugin.py
          ├── soap_subscription_sender_plugin.py
          └── mock_receiver_manager.py
```

The `.vscode/launch.json` at the **repo root** provides the VS Code debug
configuration. Its `"python"` key points at
`dev_tools/integration_hub_tester/.venv/Scripts/python.exe`.

---

## 7. How Each Service Is Invoked

The pipeline for each tab when the action button is clicked:

### HL7v2 Transformers (PHW / Chemo / PIMS / Core Reference)

```
1. plugin.run(er7_string)
        │
        │  replace \n → \r  (ER7 uses CR as segment separator)
        ▼
2. hl7apy.parser.parse_message(er7, find_groups=False)
        │  parses all segments into a flat hl7apy.Message object
        ▼
3. transform_*(msg)  or  transformer.transform_message(msg)  or  apply_core_reference_mapping(msg, ...)
        │  remaps/translates segments in place or into a new Message(version="2.5")
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
2. transform_proms_xml_to_fhir_bundle(xml)
        │  parses the WPAS PromsEventRequest XML, resolves eventCode → scenario,
        │  assembles the matching FHIR R4B Bundle (MessageHeader/Patient/... per scenario)
        ▼
3. bundle.model_dump_json()  →  pretty-printed JSON  →  output pane
```

### HL7 Server

```
1. plugin.run(er7_string)
        │
        ▼
2. parse_message(er7, find_groups=False)
        │  on parse failure → ErrorHandler(exc, er7, event_logger).reply() → generic AE NACK
        ▼
3. Produce message summary (MSH fields, segment list)
        │
        ▼
4. HL7Validator(hl7_version="2.5").validate(msg)
        │  checks HL7 version, sending app, generic rules
        │  raises ValidationException on failure → ErrorHandler(...).reply() → AR NACK
        │  any other unexpected exception            → ErrorHandler(...).reply() → AE NACK
        ▼
5. HL7AckBuilder().build_ack(control_id, msg)
        │  builds ACK message with MSA AA, mirroring sender/receiver from MSH
        ▼
6. output pane  (summary + validation result + ACK/NACK ER7)
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

### HL7 Sender ACK (classification)

```
1. plugin.run(simulated_ack_response)
        │
        ▼
2. get_ack_result(response)
        │  parses MSA-1 → SUCCESS (AA/CA) | AE | AR | INVALID
        ▼
3. output pane  (outcome, ack code, control id, retry/dead-letter behaviour)
```

### REST Server (HL7) / HL7 SOAP Server

```
1. plugin.run(er7_string)
        │
        │  REST: wraps as {"messageContent": ...} for display only
        │  SOAP: converts ER7 → HL7 v2.xml, wraps in a SOAP envelope
        ▼
2. Hl7MessageProcessor.process(...)  or  SoapMessageProcessor.process(...)
        │  real production pipeline — sender/event logger/metric sender/message
        │  store are MagicMock() no-ops, everything else runs unmodified
        ▼
3. output pane  (HTTP status + ACK/NACK or SOAP AckResponse/Fault body)
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

2. Register it in `app.py` — instantiate it and add it to the relevant category
   in `PLUGIN_CATEGORIES` (and to the flat `PLUGINS` list, used for smoke-testing):

```python
from services.my_new_plugin import MyNewPlugin

my_new_plugin = MyNewPlugin()

PLUGINS: list[ServicePlugin] = [
    ...,
    my_new_plugin,
]

PLUGIN_CATEGORIES: list[tuple[str, list[ServicePlugin]]] = [
    ("🔧 Transformers", [..., my_new_plugin]),   # ← add to the appropriate category
    ...
]
```

3. Add the service as a path dep in `pyproject.toml` and run `uv sync`. If the
   service's own `__init__`/business logic needs Azure Service Bus, WRDS, or
   similar infrastructure it can't reach locally, see
   [§5 Bypassing infrastructure dependencies](#bypassing-infrastructure-dependencies-basetransformer-service-bus-wrds)
   for the established patterns (standalone function, `MagicMock()` I/O stand-ins,
   or a local fixture file).

That's it — `ServicePage` handles all the UI automatically.

---

## 9. Updating the Tool

**If you change transformer/server/sender source files**, no reinstall is needed
— the path deps are live. Just click the action button again.

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
