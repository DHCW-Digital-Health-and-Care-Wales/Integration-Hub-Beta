# XSD Duplication Report — `hl7_validation` Resources

**Scope:** `shared_libs/hl7_validation/hl7_validation/resources/`
**Date:** 2026-07-30

## 1. Background

Schemas are organised as one directory per flow (`chemo`, `paris`, `phw`, `pims`, `wds`), each containing:

- **Base HL7 version schemas**: `<version>_fields.xsd`, `<version>_segments.xsd`, `<version>_types.xsd`
- **Trigger-event structure schemas**: `ADT_A05.xsd`, `ADT_A39.xsd`, etc.

Lookup is driven entirely by `flow_name` in [`schemas.py`](hl7_validation/schemas.py) —
`list_schemas_for_group(flow_name)` only scans that flow's own directory, so there is currently
**no code path that lets two flows share a physical schema file**. Every flow must carry its own
complete copy, even when the content is byte-identical to another flow's copy.

## 2. Confirmed duplication today (SHA-256 comparison)

| File | Flows sharing it | Identical? | Size |
|---|---|---|---|
| `2_5_fields.xsd` | `phw`, `wds` | ✅ Identical (`B31242…`) | 89,174 bytes |
| `2_5_segments.xsd` | `phw`, `wds` | ✅ Identical (`DFDEB8…`) | 142,016 bytes |
| `2_5_types.xsd` | `phw`, `wds` | ✅ Identical (`3AC154…`) | 112,031 bytes |
| `ADT_A39.xsd` | `phw`, `wds` | ✅ Identical (`214D3B…`) | 1,010 bytes |
| `ADT_A05.xsd` | `phw`, `wds` | ❌ Differs — `wds` wraps `PV1`/`PV2`/`ROL` in an optional `ADT_A05.VISIT` group; `phw` requires `PV1` inline | 2,477 vs 2,748 bytes |

**Result: 4 files (~344 KB combined) are exact, byte-for-byte duplicates between `phw` and `wds` today**, purely because both flows happen to be built on HL7 v2.5.

Other flows are not currently duplicated because no two of them share the same HL7 base version yet:

| Flow | HL7 base version | Trigger schemas |
|---|---|---|
| `chemo` | 2.4 | `ADT_A05`, `ADT_A39` |
| `phw` | 2.5 | `ADT_A05`, `ADT_A39` |
| `wds` | 2.5 | `ADT_A05`, `ADT_A39` |
| `paris` | 2.5.1 | `ADT_A05`, `ADT_A39` |
| `pims` | 2.3.1 | `ADT_A01`, `ADT_A39`, `ADT_A40` |

`ADT_A39.xsd` across `chemo`/`paris`/`pims` are similar in size (958–1,012 bytes) but **not** identical —
each is tied to its own version's base types, so they are legitimately distinct files, not accidental duplicates.

## 3. Why this matters for future flows

Any new flow that happens to use HL7 **2.4, 2.5, 2.5.1, or 2.3.1** (all four are already in use) will need to
bring in its own copy of the matching `*_fields.xsd` / `*_segments.xsd` / `*_types.xsd` triplet — each of which
is 60–140 KB of near-static, standards-derived content. With the current per-flow-directory design, this
duplication is **structural, not incidental**: it will recur every time a new flow reuses an existing HL7 version.

Trigger-event schemas (`ADT_A05.xsd`, etc.) are a separate concern — they legitimately vary per source system
(see the `phw` vs `wds` `PV1` example above), so they are less safe to blindly deduplicate.

## 4. Root cause

1. `list_schema_groups()` / `list_schemas_for_group()` treat "directory under `resources/`" and "flow" as the
   same concept, with no fallback/shared tier.
2. `xsd:include schemaLocation="..."` values in every trigger-event schema use bare filenames
   (e.g. `2_5_segments.xsd`), which only resolve because the base files are co-located in the same directory.
3. There is no documented convention (see [`README.md`](README.md)) for reusing an existing HL7 version's base
   schemas — the instructions only say "add the appropriate HL7 base XSDs for your HL7 version" per new flow,
   which encourages copy-paste.

## 5. Recommended direction (not yet implemented)

- Introduce `resources/common/<version>/` (e.g. `common/2_5/`) holding the de-duplicated base triplet.
- Update trigger-event schemas to include the shared files via a relative path
  (e.g. `schemaLocation="../common/2_5/2_5_segments.xsd"`) — `xmlschema` resolves includes relative to the
  including document, so this requires no code changes to `validate.py`.
- Exclude `common` from `list_schema_groups()` so it isn't mistaken for a validatable flow name.
- Keep trigger-event structure schemas (`ADT_A05.xsd`, `ADT_A39.xsd`, …) **per flow**, since these encode
  real per-source-system differences — only fold a flow's copy into `common/` if a byte-for-byte diff
  (as done in §2) confirms it's truly identical to another flow's, and re-check on every future change.
- Update `README.md`'s "Schema Requirements" section to instruct: *"Before adding a new HL7 base version
  triplet, check `resources/common/<version>/` first; only add a flow-local copy if the base schema doesn't
  already exist or needs flow-specific patching."*

## 6. Immediate, low-risk win available today

`phw` and `wds` can be deduplicated right now with zero behavioural change (confirmed via hash comparison):

- Move `2_5_fields.xsd`, `2_5_segments.xsd`, `2_5_types.xsd`, `ADT_A39.xsd` out of both `phw/` and `wds/` into
  `resources/common/2_5/`.
- Update the remaining flow-specific files (`phw/ADT_A05.xsd`, `wds/ADT_A05.xsd`, and the moved `ADT_A39.xsd`)
  to reference the shared files via relative `schemaLocation`.
- Run `tests/test_phw.py` and `tests/test_wds.py` to confirm no regression.

This report intentionally makes **no code changes** — it is a factual record of current duplication for
planning purposes.
