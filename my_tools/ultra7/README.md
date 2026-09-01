# Ultra7

A local developer GUI for sending HL7 v2.x / XML / JSON test messages to MLLP, REST,
and SOAP endpoints. See [../ultra7_spec.md](../ultra7_spec.md) and
[../ultra7_plan.md](../ultra7_plan.md) for the product spec and implementation plan.

## Requirements

- Python 3.13+ (3.14 supported) **with tkinter/Tk support**.
- `uv` for dependency management.

> **macOS + Homebrew gotcha:** Homebrew's `python@3.13`/`python@3.14` do not bundle
> `_tkinter`, so `uv run python app.py` will fail with
> `ModuleNotFoundError: No module named '_tkinter'` if `uv` resolves to it. Fix by
> installing a Python build that includes Tk, e.g. `uv python install 3.14`
> (uv's managed standalone build bundles Tk) — the committed `.python-version` file
> in this directory already pins `uv` to use it. Verify with:
> `uv run python -c "import tkinter; print(tkinter.TkVersion)"`.

## Run

```bash
cd my_tools/ultra7
uv sync
uv run python app.py
```

## Window layout

```
┌─────────────────────────────────────────────────────────────────┐
│ File   View   Theme                                    (menu)   │
├───┬───────────────────────────────────────────────────────────┤
│ ☰ │  (top toolbar — ☰ toggles the sidebar, works from any state) │
├───┴───────────────┬───────────────────────────────────────────┤
│ Projects           │ <project name>      [Configure Endpoint…] │
│  (sidebar)         │                                   [Save]  │
│  - New / Remove    ├───────────────────────────────────────────┤
│                    │ Message list │ Name / Format / Format btn │
│                    │  - New/Delete│ Mark/Edit Iterate Field…   │
│                    │  - ▲ / ▼     │ ┌─────────────────────────┐│
│                    │  - Enable/   │ │  message text editor    ││
│                    │    Disable   │ └─────────────────────────┘│
│                    │  - Load from │  (drag divider to resize)  │
│                    │    disk…     ├───────────────────────────  │
│                    │              │ Repeat count / Delay (ms)   │
│                    │              │ [Send] [Send Selected Once] │
│                    │              │ [Cancel]                    │
│                    │              ├───────────────────────────  │
│                    │              │ Log  [Clear] [Save to disk…]│
│                    │              │  (drag divider to resize)   │
└────────────────────┴───────────────────────────────────────────┘
```

## Usage

### Menu bar

- **File > New Project / Save Project / Exit**.
- **File > Export Selected Message(s)…** — exports the current message-list
  selection. With one message selected, opens a normal save-file dialog
  (defaulting to `.hl7`/`.xml`/`.json` based on its format). With multiple
  selected, asks for a destination folder and writes one file per message
  instead (see [Exporting messages](#exporting-messages)).
- **File > Export Messages…** — same folder-based export, but for every message
  in the current project regardless of selection.
- **View > Toggle Sidebar** — same as clicking the **☰** button in the top toolbar;
  fully hides/shows the project sidebar (no leftover strip when collapsed).
- **View > Toggle Log Panel** — shows/hides the log panel at the bottom.
- **Theme** — a radio-button list of 10 colour themes: DHCW Light (default), Dark,
  Solarized Light, Solarized Dark, Dracula, Monokai, Nord, Gruvbox Dark, One Dark,
  High Contrast. The choice is persisted to `~/.ultra7/settings.json` and restored
  on next launch. Message-editor syntax highlighting colours adapt per theme too,
  so HL7/XML/JSON tokens stay legible on both light and dark backgrounds.

### Projects (left sidebar)

- **New** — prompts for a name and creates an empty project, saved immediately.
- Click a project name to switch to it (prompts to save unsaved changes first).
- **Remove** — deletes the selected project's file from disk (with confirmation).
- Toggle the whole sidebar via the **☰** button in the top toolbar or
  **View > Toggle Sidebar** — it collapses completely, freeing all its width for
  the editor, and reopens at the same width.
- **File > Save Project** (or the **Save** button in the header) persists the
  current project's endpoint, messages, repeat count, and delay. Projects are also
  saved automatically when you switch projects or exit the app.
- Projects are stored as JSON files under `~/.ultra7/projects/` (see
  [Persistence](#persistence) below).

### Endpoint configuration

Click **Configure Endpoint…** in the header to set:

- **Kind** — `mllp`, `rest`, or `soap`.
- **Host** / **Port** — for MLLP (plain TCP + MLLP framing).
- **URL** — for REST/SOAP (must be `http://` or `https://`).
- **SOAPAction** — for SOAP requests (sent as the `SOAPAction` header).
- **Timeout (s)** — socket/request timeout.
- **Headers** — one `Name: Value` pair per line (REST/SOAP).

### Messages (message list, left of the editor)

- **Multi-select** — click to select one message, or use Shift-click / Ctrl-click
  (Cmd-click on macOS) to select a range or several individual messages, the same
  as most desktop file lists. The text editor always shows the content of the
  last-clicked ("active") message; **Disable/Enable**, **Export Selected
  Message(s)…**, and **Send Selected Once** all act on the *entire* current
  selection, not just the active one.
- **New** — adds a blank message; **Delete** removes the selected one.
- **▲ / ▼** — reorder messages within the project.
- **Disable / Enable** — bulk-toggles every selected message: if any of them are
  enabled, disabling wins (all become disabled); otherwise all become enabled.
  Disabled messages show a `[off]` prefix and a muted grey colour in the list.
  This only affects batch **Send** — **Send Selected Once** always sends the
  selected messages regardless of their enabled/disabled state.
- **Load from disk…** — imports a file's contents as a new message (format is
  auto-detected as HL7 / XML / JSON, with syntax highlighting).
- Each message has an editable **Name** and **Format** override.
- **Format** button — pretty-prints (re-indents) the message body for XML and JSON
  messages; shows an error dialog instead of changing anything if the content
  doesn't parse. Not available for HL7 (ER7 has no standard indentation). If an
  iteration field is marked, it's relocated to follow its highlighted text after
  formatting — if that text can't be found unambiguously in the reformatted
  content, the iteration field is cleared and you're notified.
- Segments are normalized to `\r` automatically when sent over MLLP, so pasted or
  loaded files with `\n`/`\r\n` line endings still work correctly.

### Iteration field (changing part of a message on each repeat send)

Highlight a portion of the message text (e.g. a control ID or patient identifier)
and click **Mark Iterate Field** to set it as the part that changes on every repeat
send. This is saved per message and persisted with the project. Use **Edit Iterate
Field…** to change the mode/parameters (or remove it) without needing to re-select
the text — it's enabled whenever the current message has one set. Supported modes:

- **increment** — parses the highlighted text as an integer and adds `step × send
  number` each time; **Pad width** controls zero-padding (`0` keeps the original
  width, e.g. `000001` stays 6 digits as it counts up).
- **list** — cycles through a set of values (one per line), wrapping around once
  exhausted.
- **timestamp** — replaces the highlighted text with the current time, formatted
  using the given `strftime` format string.

The marked region is shown with a highlighted background in the editor and tracks
further edits to the message (it moves correctly if you type before/after it).
Re-open **Iterate Field…** with the same (or a new) selection to change the mode,
or use **Remove** in that dialog to clear it. If the highlighted text is deleted,
the iteration field is cleared automatically.

### Sending

- **Repeat count** / **Delay (ms)** — how many times to send all *enabled*
  messages in order, and the pause between each send.
- **Send** — sends every enabled message in the project that many times; if none
  are enabled, the status shows "No enabled messages to send" and nothing is sent.
- **Send Selected Once** — sends every currently *selected* message (see
  Multi-select above) exactly once each, ignoring the repeat count, the delay, and
  the enabled/disabled toggle. If nothing is selected, the status shows
  "No message selected".
- **Cancel** — stops an in-progress send (either button).
- Messages with an iteration field get their highlighted portion recomputed for
  each send (using the current repeat index; **Send Selected Once** always uses
  the first/base value).
- MLLP sends validate the ACK's `MSA-1` code (`AA`/`CA` = success); anything else,
  or no ACK at all, is reported as a failure.

### Exporting messages

- **File > Export Selected Message(s)…** — exports the current message-list
  selection: a single save-file dialog if exactly one message is selected, or a
  folder-based export (one file per message) if more than one is selected.
- **File > Export Messages…** — same folder-based export for every message in the
  project, regardless of selection.
- Each file's extension matches its message's format (`.hl7` / `.xml` / `.json`).
  Filenames are derived from the message name, sanitized to remove characters
  that aren't valid in filenames, and disambiguated with `(2)`, `(3)`, … if two
  messages share a name.

### Log panel

- Toggle visibility via **View > Toggle Log Panel**.
- Before each send, a grey info line announces it: e.g.
  `Sending A01 [2/5] to 127.0.0.1 on port 2575` (MLLP) or
  `Sending A01 [1/1] to example.test on port 443` (REST/SOAP, parsed from the URL).
- The result line immediately below shows a `HH:MM:SS.mmm` timestamp, the
  message/iteration label, OK/ERROR status, latency, and the response or error
  detail. A blank line separates each send's info+result pair from the next.
- **Clear** empties the log.
- **Save to disk…** writes the log's current contents to a chosen file.
- Drag the divider above the log panel to resize it relative to the message editor.

## Persistence

- **Projects** — JSON files under `~/.ultra7/projects/`, one per project. Each
  stores the endpoint configuration (MLLP / REST / SOAP), the ordered list of
  messages (with format, iteration field, and enabled/disabled state), and the
  repeat count / delay used when sending.
- **Settings** — `~/.ultra7/settings.json`, currently just the selected colour theme.

## Tests

```bash
uv run python -m unittest discover tests
```
