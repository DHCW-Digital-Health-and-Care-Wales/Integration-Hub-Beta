"""Structured, searchable built-in help documentation for Ultra7."""
from __future__ import annotations

import sys
from dataclasses import dataclass

from ultra7.formats.hl7_dictionary import FIELD_NAMES, SEGMENT_NAMES


@dataclass(frozen=True)
class HelpTopic:
    """A single topic displayed in Ultra7's built-in Help browser."""

    id: str
    title: str
    category: str
    summary: str
    body: str


def platform_accel() -> str:
    return "Cmd" if sys.platform == "darwin" else "Ctrl"


def get_shortcuts(accel: str | None = None) -> tuple[tuple[str, str], ...]:
    mod = accel or platform_accel()
    return (
        (f"{mod}+S", "Save current project"),
        (f"{mod}+,", "Open Preferences (themes, fonts, sizes, editor options)"),
        (f"{mod}+Return", "Send Selected Once"),
        (f"{mod}+F", "Open Find & Replace bar in editor"),
        (f"{mod}+Shift+F", "Pretty Print XML / JSON message"),
        (f"{mod}+B", "Toggle left Projects sidebar"),
        (f"{mod}+T", "Toggle Messages / Structure tree view"),
        (f"{mod}+L", "Toggle bottom Activity Log panel"),
        (f"{mod}++ / {mod}+-", "Increase / decrease editor font size"),
        (f"{mod}+0", "Reset editor font size to default"),
        ("F1", "Open Built-in Help Guide"),
        ("Escape", "Close Find bar or cancel inline tree edit"),
    )


def _build_hl7_reference_body() -> str:
    lines = [
        "# HL7 v2.x Quick Reference",
        "",
        "## Framing & Delimiters",
        "- MLLP start block: `0x0B` (`<VT>`), end block: `0x1C 0x0D` (`<FS><CR>`).",
        "- Segments are separated by Carriage Return (`\\r`). Ultra7 normalises `\\n` and `\\r\\n` "
        "automatically when sending over MLLP.",
        "- Default encoding characters (`MSH-1` & `MSH-2`): field `|`, component `^`, repetition `~`, "
        "escape `\\`, subcomponent `&`.",
        "- MLLP ACK validation treats `MSA-1` codes `AA` (Application Accept) and `CA` (Commit Accept) "
        "as OK; `AE`, `AR`, `CE`, `CR`, or missing ACK are reported as errors.",
        "",
        "## Common Segments",
    ]
    for code in ("MSH", "EVN", "PID", "PD1", "NK1", "PV1", "ORC", "OBR", "OBX", "NTE", "MRG", "MSA", "ERR"):
        if code in SEGMENT_NAMES:
            lines.append(f"- `{code}` — {SEGMENT_NAMES[code]}")
    lines.extend(["", "## Key Clinical Fields"])
    for field_id in (
        "MSH-7",
        "MSH-9",
        "MSH-10",
        "PID-3",
        "PID-5",
        "PID-5.1",
        "PID-5.2",
        "PID-7",
        "PID-8",
        "PID-11",
        "PV1-2",
        "PV1-3",
        "PV1-19",
        "OBX-3",
        "OBX-5",
        "MSA-1",
        "MSA-2",
    ):
        if field_id in FIELD_NAMES:
            lines.append(f"- `{field_id}` — {FIELD_NAMES[field_id]}")
    return "\n".join(lines)


def _build_shortcuts_body(accel: str | None = None) -> str:
    lines = [
        "# Keyboard Shortcuts",
        "",
        "Use these shortcuts anywhere in the main Ultra7 window:",
        "",
    ]
    for key, desc in get_shortcuts(accel):
        lines.append(f"- `{key}` — {desc}")
    lines.extend([
        "",
        "## Mouse & Tree Shortcuts",
        "- Double-click a leaf node in **Structure** view — edit its value inline.",
        "- Double-click a result row in **Activity Log** — open the full **Response Inspector**.",
        "- Click the path in the bottom editor status bar — copy the HL7 path / XPath / JSONPath to the clipboard.",
        "- Shift-click or Cmd/Ctrl-click in **Messages** — multi-select messages for bulk Disable/Enable, "
        "Delete, Export, Compare, or Send Selected Once.",
    ])
    return "\n".join(lines)


def build_help_topics(accel: str | None = None) -> tuple[HelpTopic, ...]:
    """Return all built-in help topics in display order."""
    mod = accel or platform_accel()
    return (
        HelpTopic(
            id="getting-started",
            title="Getting Started",
            category="Basics",
            summary="Overview, quick workflow, themes, and where files are saved.",
            body=(
                "# Welcome to Ultra7\n"
                "\n"
                "Ultra7 is a local developer desktop GUI for composing, inspecting, and sending HL7 v2.x, "
                "XML, and JSON test messages to MLLP, REST, and SOAP endpoints.\n"
                "\n"
                "## Quick Start\n"
                "1. Click **+ New** in the left sidebar to create a project (or open an existing project).\n"
                "2. Click **Configure Endpoint…** in the header and choose an Integration Hub preset or enter "
                "your host/port or URL. Click **Test Connection** to verify reachability.\n"
                "3. Click **+ New** or **Load from disk…** in the Messages panel to add test payloads.\n"
                "4. Click **▶ Send** to send all enabled messages (with Repeat & Delay), or **Send Selected Once** "
                "to fire the highlighted message(s) once.\n"
                "\n"
                "## Persistence, Themes & Preferences\n"
                "- Projects are saved as JSON files under `~/.ultra7/projects/`.\n"
                "- App preferences (theme, UI/editor fonts, sizes, word wrap, and Structure tree options) "
                "are stored in `~/.ultra7/settings.json`.\n"
                "- Switch between 15 built-in light and dark themes (including DHCW Light, DHCW Dark, "
                "GitHub Light, Catppuccin, and Tokyo Night) in the **Theme** menu, or press "
                f"`{mod}+,` to open **Preferences…** for live theme swatches and typography settings."
            ),
        ),
        HelpTopic(
            id="projects-batch",
            title="Projects & Batch Runs",
            category="Basics",
            summary="Managing projects and running multiple projects sequentially.",
            body=(
                "# Projects & Batch Runs\n"
                "\n"
                "## Managing Projects\n"
                "- Click any project name in the left sidebar to open it. Unsaved edits are saved automatically "
                "when switching projects or exiting.\n"
                f"- Use **Save** (`{mod}+S`) at any time to persist messages, endpoint settings, "
                "repeat count, and delay.\n"
                f"- Click **☰** (`{mod}+B`) to collapse the project sidebar completely for maximum editing space.\n"
                "\n"
                "## Running Multiple Projects\n"
                "- Tick the checkboxes next to one or more projects in the sidebar, then click **▶ Run**.\n"
                "- Ultra7 runs each checked project in sequence using its own endpoint, enabled messages, "
                "repeat count, and delay.\n"
                "- Click **■ Cancel** in the Send Controls bar to stop an active batch run immediately "
                "(even during a delay pause)."
            ),
        ),
        HelpTopic(
            id="endpoints",
            title="Endpoints, Presets & Testing",
            category="Networking",
            summary="Configuring MLLP, REST, SOAP endpoints and Integration Hub presets.",
            body=(
                "# Endpoints, Presets & Testing\n"
                "\n"
                "Click **Configure Endpoint…** in the top header to edit the active project's destination. "
                "The configured endpoint is always shown as a live summary directly under the project title.\n"
                "\n"
                "## Supported Protocols\n"
                "- **MLLP** — Plain TCP socket with HL7 MLLP framing (`0x0B` ... `0x1C 0x0D`). "
                "Automatically normalises line endings to `\\r`.\n"
                "- **REST** — HTTP/HTTPS `POST` with automatic `Content-Type` (`application/hl7-v2`, "
                "`application/xml`, or `application/json`, overridable via custom Headers).\n"
                "- **SOAP** — HTTP/HTTPS `POST` with `SOAPAction` header. Raw XML bodies are wrapped in a "
                "SOAP 1.1 `<soap:Envelope>` automatically unless an Envelope is already present.\n"
                "\n"
                "## MLLP Streaming Modes (HL7 Server Compatible)\n"
                "For MLLP endpoints, switch delivery mode directly in the **Send Controls** bar (**MLLP** "
                "dropdown) or in **Configure Endpoint…**:\n"
                "- **Per message** — Default. Opens and closes a fresh TCP socket for each message.\n"
                "- **Stream (1 TCP)** — Keeps one persistent TCP connection open across all messages and "
                "repeats in a run, sending each MLLP frame and reading its ACK on the same socket before "
                "closing cleanly with EOF. Matches `hl7_server`'s persistent MLLP handler.\n"
                "- **Pipelined burst** — Writes every MLLP frame back-to-back onto one TCP stream before "
                "draining all ACKs in order, directly exercising multi-frame stream buffering on `hl7_server`.\n"
                "\n"
                "## Integration Hub Presets\n"
                "Use the **Preset** dropdown at the top of the Endpoint dialog for one-click local "
                "Docker Compose ports:\n"
                "- PHW → MPI (`127.0.0.1:2575`)\n"
                "- CAV Paris → MPI (`127.0.0.1:2577`)\n"
                "- ChemoCare → MPI (`127.0.0.1:2578`)\n"
                "- PIMS → MPI (`127.0.0.1:2579`)\n"
                "- Mosaiq → MPI (`127.0.0.1:2583`)\n"
                "- RISP → WRRS REST (`http://127.0.0.1:8080/hl7`)\n"
                "- WPAS → PROMS SOAP (`http://127.0.0.1:8081/soap`)\n"
                "- Ultra7 Mock MLLP (`:2599`) and Mock HTTP (`:8090`)\n"
                "\n"
                "## Unconfigured Flows & Test Connection\n"
                "- New projects without an endpoint highlight **Configure Endpoint…** in the header and "
                "prompt you automatically if you click **▶ Send** or **Send Selected Once** first.\n"
                "- Click **Test Connection** inside the Endpoint dialog to verify TCP reachability (MLLP) "
                "or HTTP reachability (REST/SOAP) with live latency before sending."
            ),
        ),
        HelpTopic(
            id="messages-editor",
            title="Messages, Find & Status Bar",
            category="Editor",
            summary="Multi-select, Pretty Print, Find & Replace, Export, and Live Path Bar.",
            body=(
                "# Messages & Editor\n"
                "\n"
                "## Message List Actions\n"
                "- **Multi-select** with Shift-click or Cmd/Ctrl-click to bulk **Disable/Enable**, **Delete**, "
                "reorder (**▲ / ▼**), **Compare**, **Export**, or **Send Selected Once**.\n"
                "- Disabled messages appear with an `[off]` prefix and are skipped by batch **▶ Send**, "
                "while **Send Selected Once** always sends your selection.\n"
                "- **Load from disk…** imports one or more files at once with automatic format detection "
                "(JSON → XML → HL7).\n"
                "- Use **File > Export Selected Message(s)…** or **Export Messages…** to save messages back "
                "to disk with matching `.hl7`/`.xml`/`.json` extensions.\n"
                "\n"
                "## Formatting & Find / Replace\n"
                f"- **Pretty Print** (`{mod}+Shift+F`) re-indents XML and JSON payloads and relocates "
                "marked iteration fields.\n"
                f"- Press `{mod}+F` (or click **Find**) to open the inline **Find & Replace** bar with "
                "case-sensitivity (`Aa`), match counter, Prev/Next, Replace, and Replace All.\n"
                "\n"
                "## Live Status Bar\n"
                "The status bar below the editor displays the current cursor's exact HL7 path & description "
                "(e.g. `PID-5.2 · Given Name`), XPath (`/Patient/Name`), or JSONPath (`$.patient.name`), "
                "alongside `Ln/Col` and byte size. Click the path to copy it to your clipboard."
            ),
        ),
        HelpTopic(
            id="structure-tree",
            title="Structure Tree & Inline Editing",
            category="Editor",
            summary="Two-way synced collapsible HL7/XML/JSON tree with filter and inline editing.",
            body=(
                "# Structure Tree & Inline Editing\n"
                "\n"
                "Switch the left panel of the project view between **Messages** and **Structure** using "
                f"the toggle buttons at the top of the panel (or `{mod}+T`). Drag the divider between "
                "the tree and editor to resize.\n"
                "\n"
                "## Supported Formats\n"
                "- **HL7 v2.x** — Segments → Fields → Repetitions → Components → Subcomponents, annotated "
                "with built-in HL7 field names (e.g. `PID-3 · Patient Identifier List`, "
                "`MSH-10 · Message Control ID`).\n"
                "- **XML** — Nested `<Elements>` and `@attributes` with exact XPath locations.\n"
                "- **JSON** — Objects, arrays, keys, and scalar values with JSONPath locations.\n"
                "\n"
                "## Two-Way Selection Sync\n"
                "- Click any node in the tree to highlight and scroll to its exact text span in the code editor.\n"
                "- Click or move the cursor in the code editor to automatically expand and select the deepest "
                "matching node in the tree.\n"
                "\n"
                "## Filter & Inline Value Editing\n"
                "- Type into the **Filter** box to narrow the tree by field code, HL7 description, "
                "tag name, or value.\n"
                "- Use **Expand** / **Collapse** to open or fold all branches at once.\n"
                "- **Double-click** any leaf value in the tree to edit it inline — pressing `Enter` updates "
                "the exact span in the code editor immediately."
            ),
        ),
        HelpTopic(
            id="iteration-fields",
            title="Iteration Fields & NHS Numbers",
            category="Testing",
            summary="Mark multiple dynamic fields per message and preview sends before firing.",
            body=(
                "# Iteration Fields & NHS Number Generator\n"
                "\n"
                "Highlight any substring in the editor — **or select a leaf node in the Structure tree** — "
                "and click **+ Mark Field** to recompute that span on each repeat send (when **Repeat > 1**). "
                "You can mark **multiple** non-overlapping fields on the same message (for example: "
                "incrementing `MSH-10`, live-stamping `MSH-7`, and generating a fresh NHS Number in `PID-3`).\n"
                "\n"
                "## Iteration Modes\n"
                "- **increment** — Parses the marked text as an integer and adds `step × send_index`. "
                "Set `Pad width = 0` to keep the original zero-padded width (e.g. `000001` → `000002`).\n"
                "- **list** — Cycles through a list of values (one per line), wrapping around when exhausted.\n"
                "- **timestamp** — Inserts the current timestamp formatted with `strftime` "
                "(with quick presets for HL7, ISO, and Date formats).\n"
                "- **nhs_number** — Generates a valid 10-digit synthetic UK NHS Number (`999…` test range) "
                "passing the official Modulus 11 check-digit algorithm. Preserves spacing if the marked "
                "text contained spaces.\n"
                "\n"
                "## Managing & Previewing\n"
                "- **Edit Field…** — Edits the field at your cursor (or opens **Manage All…** if multiple exist).\n"
                "- **Manage All…** — Shows a table of every marked field with live `#1 → #2` examples, "
                "**Edit…**, **Jump to Text**, **Remove**, and **Clear All**.\n"
                "- **Clear All** — Removes all iteration fields from the current message in one click.\n"
                "- **Preview Sends…** — Highlights the exact generated values across Sends `#1..N` before sending."
            ),
        ),
        HelpTopic(
            id="pii-scrubber",
            title="PII Scrubber (Anonymiser)",
            category="Testing",
            summary="One-click clinical de-identification preserving structure & Mod-11 NHS numbers.",
            body=(
                "# One-Click PII Scrubber\n"
                "\n"
                "Click **Scrub PII** in the editor toolbar (or **Tools > Scrub PII (Anonymise)**) to "
                "replace sensitive patient data with safe synthetic test values before saving or "
                "sharing a message.\n"
                "\n"
                "## What Gets Scrubbed\n"
                "- **HL7 v2.x** — `PID-2`/`PID-3`/`PID-19` (replaces NHS numbers with valid Mod-11 `999…` "
                "synthetic numbers while keeping assigning authorities like `^^^NHS^NH`), "
                "`PID-5`/`PID-6`/`PID-9` (names), `PID-7` (DOB), `PID-11` (address), `PID-13`/`PID-14` "
                "(phone numbers), plus `NK1` and `MRG` patient identifiers/names.\n"
                "- **XML** — Clinical PII tags such as `<NHSNumber>`, `<Surname>`, `<Forename>`, "
                "`<DateOfBirth>`, `<Address>`, `<Postcode>`, `<Telephone>`, and `<Email>`.\n"
                "- **JSON / FHIR** — Matching PII keys (`family`, `given`, `birthDate`, `line`, "
                "`postalCode`, `email`, `phone`) and FHIR `Identifier` entries using an NHS Number system URI."
            ),
        ),
        HelpTopic(
            id="sending-log",
            title="Sending, Stats & Response Inspector",
            category="Networking",
            summary="Batch metrics, Response Inspector popup, and saving logs.",
            body=(
                "# Sending, Activity Log & Response Inspector\n"
                "\n"
                "## Send Controls\n"
                "- **Repeat** & **Delay (ms)** — Number of iterations for all enabled messages and pause "
                "between sends.\n"
                "- **MLLP** — Inline delivery mode selector for MLLP endpoints: **Per message** (fresh TCP "
                "socket each send), **Stream (1 TCP)** (single persistent TCP stream), or **Pipelined burst** "
                "(all frames written back-to-back on one stream). Automatically disabled for REST/SOAP.\n"
                "- **▶ Send** — Sends every enabled message in order for `Repeat` rounds (prompts to "
                "configure an endpoint first if the project does not have one yet).\n"
                f"- **Send Selected Once** (`{mod}+Return`) — Fires every selected message once immediately, "
                "ignoring Repeat, Delay, and `[off]` state.\n"
                "- **■ Cancel** — Stops an in-progress single send or multi-project batch immediately.\n"
                "\n"
                "## Live Batch Stats & Response Inspector\n"
                "- The Activity Log header tracks live stats across sends: total sent, OK count, ERR count, "
                "average latency, and **P95 latency** (reset with **Clear**).\n"
                "- **Double-click** any result row in the log to open the **Response Inspector**, showing "
                "the full syntax-highlighted, pretty-printed ACK / XML / JSON response with a **Copy** button.\n"
                "- Click **Save Log…** to write the log contents to a `.log` file."
            ),
        ),
        HelpTopic(
            id="diff-viewer",
            title="Compare Messages (Diff)",
            category="Tools",
            summary="Side-by-side message comparison with synchronized scrolling.",
            body=(
                "# Compare Messages (Side-by-Side Diff)\n"
                "\n"
                "Open **Tools > Compare Messages…** to compare any two messages in the current project "
                "side by side.\n"
                "\n"
                "## Tips\n"
                "- If you multi-select two messages in the **Messages** list before opening "
                "**Compare Messages…**, both panes are pre-filled automatically.\n"
                "- Use the **Left** and **Right** dropdowns at the top to switch between any messages "
                "in the project.\n"
                "- Both panes scroll together and highlight added (green), removed (red), and modified "
                "(amber) lines along with a `+N / -M` summary."
            ),
        ),
        HelpTopic(
            id="mock-receiver",
            title="Built-in Mock Receiver",
            category="Tools",
            summary="Local MLLP and HTTP/SOAP listener with live capture and project import.",
            body=(
                "# Built-in Mock MLLP & HTTP Receiver\n"
                "\n"
                "Open **Tools > Mock Receiver…** to launch a local test listener directly inside Ultra7 "
                "— no Docker container required.\n"
                "\n"
                "## Modes\n"
                "- **MLLP** — Listens on TCP (default `127.0.0.1:2599`), accepts single or persistent "
                "multi-message MLLP streams (including pipelined frames on one socket), reads `MSH-10`, "
                "and replies with a valid HL7 ACK using your chosen `MSA-1` code (`AA`, `CA`, `AE`, or `AR`).\n"
                "- **HTTP** — Listens on HTTP (default `127.0.0.1:8090`), accepts `POST`/`HEAD` requests, "
                "and responds with your configured HTTP status code and response body.\n"
                "- Optional **Delay (ms)** lets you test sender timeouts and slow-downstream behaviour.\n"
                "\n"
                "## Inspect & Import\n"
                "- Incoming messages appear live in the **Received Messages** list with syntax-highlighted "
                "payload preview.\n"
                "- Click **Import to Project** to copy any captured payload straight into your active "
                "Ultra7 project."
            ),
        ),
        HelpTopic(
            id="hl7-reference",
            title="HL7 v2.x Quick Reference",
            category="Reference",
            summary="MLLP framing, delimiters, ACK codes, and common NHS Wales segments/fields.",
            body=_build_hl7_reference_body(),
        ),
        HelpTopic(
            id="shortcuts",
            title="Keyboard Shortcuts",
            category="Reference",
            summary="All keyboard and mouse shortcuts for fast navigation.",
            body=_build_shortcuts_body(mod),
        ),
    )


def search_help_topics(query: str, topics: tuple[HelpTopic, ...] | None = None) -> list[HelpTopic]:
    """Filter help topics by case-insensitive substring match across title, category, summary, and body."""
    all_topics = topics if topics is not None else build_help_topics()
    needle = query.strip().lower()
    if not needle:
        return list(all_topics)
    return [
        topic
        for topic in all_topics
        if needle in topic.title.lower()
        or needle in topic.category.lower()
        or needle in topic.summary.lower()
        or needle in topic.body.lower()
    ]
