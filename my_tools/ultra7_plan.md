# Ultra7 — Implementation Plan

Based on [ultra7_spec.md](ultra7_spec.md).

## 1. Overview

Ultra7 is a standalone desktop GUI tool (lives under `my_tools/ultra7/`, alongside
`integration_hub_tester/` and `proms_tester/`) for sending HL7 v2.x / XML / JSON test
messages to MLLP, REST, and SOAP endpoints, with project persistence, message replay,
repeat/delay control, and a minimum-delay probing function.

It is a developer tool, not a deployed service — no Dockerfile, no shared_libs
dependency, no Azure Service Bus involvement. It follows the same conventions as the
other tools in `my_tools/`.

## 2. Tech Stack

- **Python 3.13**, managed with `uv` (`pyproject.toml` + `uv.lock`, `uv run app.py`).
- **tkinter** for the GUI (consistent with `integration_hub_tester`), using `ttk` widgets.
- **Syntax highlighting**: a lightweight custom `Text` widget tagger (regex-based, per
  format) rather than pulling in a heavyweight editor dependency — mirrors the
  "avoid adding new dependencies unless clearly needed" convention. `pygments` may be
  used purely for tokenizing (no rendering) if plain regex tagging proves insufficient.
- **hl7apy** for HL7 v2.x parsing/validation (already used elsewhere in the repo).
- Standard library `socket` for MLLP, `http.client`/`urllib.request` (or `requests` if
  already a transitive dep) for REST, and `xml.etree.ElementTree` + manual SOAP
  envelope templating for SOAP.
- **DHCW brand colours** (`#325083`, `#12A3C9`, `#1B294A`, `#F8CA4D`) and Rubik font for
  the UI, per repo-wide UI convention.
- Project persistence as JSON files on disk under a user config directory
  (e.g. `~/.ultra7/projects/<project-name>.json`).

## 3. Project Structure

```
my_tools/ultra7/
├── README.md
├── pyproject.toml
├── uv.lock
├── app.py                     # entry point — window chrome, layout, wiring
├── ultra7/
│   ├── __init__.py
│   ├── models.py               # Project, Endpoint, Message dataclasses
│   ├── storage.py               # load/save projects to disk (JSON)
│   ├── senders/
│   │   ├── __init__.py
│   │   ├── base.py              # Sender protocol: send(message) -> Response
│   │   ├── mllp_sender.py       # TCP/MLLP client
│   │   ├── rest_sender.py       # HTTP client
│   │   └── soap_sender.py       # SOAP client
│   ├── formats/
│   │   ├── __init__.py
│   │   ├── detect.py             # sniff HL7/XML/JSON from message text
│   │   └── highlighting.py       # Text widget tag rules per format
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── sidebar.py            # collapsible project tree
│   │   ├── editor_pane.py        # message text area + format toolbar
│   │   ├── log_panel.py          # bottom togglable send/response log
│   │   ├── endpoint_dialog.py    # configure endpoint (type/url/port)
│   │   └── send_controls.py      # repeat count, delay, min-delay probe
│   └── delay_probe.py            # binary-search/step-down min delay finder
└── tests/
    ├── __init__.py
    ├── test_models.py
    ├── test_storage.py
    ├── test_detect.py
    ├── test_senders.py
    └── test_delay_probe.py
```

## 4. Data Model (`models.py`)

```python
Message:
    id: str                # stable id, used for iteration/ordering
    name: str
    format: Literal["hl7", "xml", "json"]
    content: str
    sequence_id: str | None  # optional id selected for repeat-send iteration

Endpoint:
    kind: Literal["mllp", "rest", "soap"]
    host: str | None         # MLLP
    port: int | None         # MLLP
    url: str | None          # REST / SOAP
    headers: dict[str, str]  # REST / SOAP
    soap_action: str | None  # SOAP

Project:
    name: str
    endpoint: Endpoint
    messages: list[Message]  # ordered; order is user-editable
    repeat_count: int = 1
    delay_ms: int = 0
```

`storage.py` handles JSON (de)serialization and atomic writes (write to temp file,
`os.replace`) to avoid corrupting a project file on crash.

## 5. UI Layout

- **Left sidebar** — collapsible tree of projects (`ttk.Treeview` or nested frames).
  Supports: new project, open project, remove project (with confirmation), rename.
- **Main pane** — message editor:
  - Text area (`tk.Text`) with format-aware syntax highlighting.
  - Toolbar: format selector (HL7/XML/JSON, auto-detect default), "Pretty print /
    Format", load-from-disk, new message, delete message, reorder (up/down or
    drag-and-drop within the message list).
  - Message list for the active project (ordered), each row shows name + assigned
    sequence id, selectable/reorderable.
- **Right/top panel** — endpoint configuration (kind, host/port or URL, SOAP action,
  headers) via `endpoint_dialog.py`.
- **Send controls** — repeat count field, delay (ms) field, "Send" button, "Find Min
  Delay" button, progress indicator during send/probe runs.
- **Bottom panel** — togglable log of sends/responses (timestamp, message id, request
  summary, response status/body, latency). Auto-scroll with a pause/clear option.

## 6. Sending & Protocols

- **MLLP** (`mllp_sender.py`): open TCP socket, wrap payload in `\x0b ... \x1c\r`
  framing (reuse the framing constants already documented in
  `integration_hub_tester/services/hl7_sender_plugin.py`), read ACK until MLLP
  end block or timeout, report round-trip latency.
- **REST** (`rest_sender.py`): configurable method (default POST), headers,
  content-type inferred from message format, capture status code/body/latency.
- **SOAP** (`soap_sender.py`): wrap payload in a configurable SOAP envelope template,
  POST with `SOAPAction` header, capture response.
- All senders implement a common `Sender.send(message: Message) -> SendResult`
  protocol so `send_controls.py` and `delay_probe.py` are protocol-agnostic.

## 7. Repeat / Delay / Min-Delay Probe

- **Repeat send**: send each message (or a selected message by sequence id) N times
  with a fixed delay between sends; log each attempt.
- **Min delay finder** (`delay_probe.py`): start from a configurable initial delay,
  systematically reduce it (e.g. halving, then linear step-down near the failure
  boundary) sending probe messages at each step until an error/timeout/non-ACK
  response occurs; report the last known-good delay. Must be cancellable and run off
  the UI thread (background thread + queue-based UI updates) so the GUI stays
  responsive.

## 8. Format Detection & Syntax Highlighting

- `detect.py`: sniff order — JSON (`json.loads` succeeds), XML (starts with `<?xml`
  or root tag parses), otherwise HL7 (starts with `MSH|`). Manual override always
  available via the toolbar.
- `highlighting.py`: regex-based tagging per format (HL7 segment/field delimiters,
  XML tags/attributes, JSON keys/strings/numbers), applied on keystroke via a debounced
  `<<Modified>>` binding.

## 9. Persistence Details

- One JSON file per project under `~/.ultra7/projects/`.
- Sidebar lists files found in that directory at startup; refreshed on
  create/remove.
- Save triggers: explicit "Save", and on project switch/app exit (prompt if dirty).

## 10. Testing

- Follow repo convention: `unittest`, tests under `tests/`, named `test_*.py`.
- Cover: model (de)serialization round-trips, format detection edge cases (empty
  input, ambiguous content), MLLP framing correctness, delay-probe step-down logic
  (mocked sender), storage atomicity (simulated write failure).
- Manual/UI testing only (no automated GUI tests) given `tkinter`.

## 11. Milestones

1. Scaffold project (`pyproject.toml`, `app.py` shell, DHCW-themed window chrome).
2. Data model + storage (load/save projects), sidebar CRUD wired to storage.
3. Message editor pane: text area, format detection, load-from-disk, syntax highlighting.
4. Endpoint configuration dialog (MLLP/REST/SOAP).
5. Senders (MLLP → REST → SOAP) with a manual single-send button and log panel.
6. Repeat count + delay controls, ordered message iteration by sequence id.
7. Min-delay probe function (background thread, cancellable).
8. Polish: reordering messages/projects, error handling, README, unit tests throughout.

## 12. Open Questions (needs product/team input before finalizing)

- Exact SOAP envelope template — is there a standard WSDL/envelope shape to match,
  or fully user-configurable per endpoint?
- ACK validation depth for MLLP (accept any `\x0b...\x1c` framed response, or
  parse and validate `MSA-1` accept/reject code?)
- Should sent/received messages be persisted as history, or only live in the log
  panel for the current session?
