# hl7_message_processor

Version- and message-structure-aware HL7 v2 ER7 &lt;-&gt; XML conversion and XSD validation.

Selects the XSD schema to use from the message itself:

- **Version**: `MSH-12.1`, normalised to a folder key (`2.5.1` -> `2_5_1`).
- **Structure**: `MSH-9.3` if present, else derived from `MSH-9.1`/`MSH-9.2` (message code + trigger
  event) via a version-agnostic alias table (`trigger_structure_map.py`).

The resolved `(version, structure)` pair is looked up first under `custom_schemas/<version>/`, falling
back to `schemas/<version>/` (the standard schema is the default; a custom schema is only used for the
specific structures that actually have one — there is no "prefer custom" precedence, since custom and
standard schemas are never named the same). If no schema can be found for the resolved `(version,
structure)`, or the message doesn't fit the resolved schema's grammar, the library logs an error and
raises `MessageNotProcessableError` — it never falls back to a flat/best-effort conversion.

This library has **no dependency on `hl7_validation`** (see
`notes/hl7-message-processor-design-report.md` in the repo root for the full design rationale). It does
depend on `hl7apy` (ER7 parsing) and `field-utils-lib` (safe HL7 field access), both already used
elsewhere in this repo.

## Public API

```python
from hl7_message_processor import (
    process_er7,          # ER7 string -> ProcessedMessage (xml, structure_id, version, xsd_path)
    validate_xml,          # xml string + xsd path -> None, raises XmlValidationError
    xml_to_er7,            # v2.xml string -> ER7 string
    MessageNotProcessableError,
    XmlValidationError,
)

result = process_er7(er7_string)
validate_xml(result.xml, result.xsd_path)
```

## Design notes

- `xsd_structure.py` parses a structure XSD (either the standard *modular* shape under `schemas/`, or
  the *self-contained* shape used by `custom_schemas/`) into a **recursive** grammar tree (`SegmentItem` /
  `GroupItem`, arbitrary depth) — this is the fix for the "only one level of group nesting" defect
  confirmed in `hl7_validation.convert` (see the design report, section 3.2/4.2).
- `matcher.py` runs a greedy recursive-descent match of the flat ER7 segment list against that tree,
  producing a matched layout of the same nesting depth as the grammar — mirroring the approach used by
  `ForTesting/hl7-rust-main`'s `hl7-2` crate. A message that doesn't fit the grammar fails loudly
  (`MessageNotProcessableError`) rather than being flattened.
- `converter.py` renders XML by recursing over the matched layout (ER7 -> XML), and separately converts
  XML -> ER7 using the ".` in tag name => group, else segment" rule (no schema needed for that
  direction).

## Development

```bash
uv sync
bash check.sh   # ruff, bandit, mypy, unittest
```
