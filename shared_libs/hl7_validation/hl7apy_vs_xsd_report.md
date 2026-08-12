# HL7 Validation: `hl7apy` Built-in Validation vs. XSD Schema Validation

**Scope:** `shared_libs/hl7_validation/`
**Date:** 2026-08-03 (updated same day after empirical verification against `hl7apy` 1.3.5 source)

## 1. Question

Can the flow-specific XSD schema validation (`validate_er7_with_flow_schema`) be replaced by
`hl7apy`'s built-in message validation (`msg.validate()` / `validate_er7_with_standard`), removing
the need to maintain and read XSD files? A follow-up claim was raised: *the current flow XSDs are
standard structures, not custom ones, so this should be possible today.*

## 2. Answer

**Mostly correct, verified.** Having installed `hl7apy==1.3.5` locally and diffed its bundled
structure definitions (`v2_4`, `v2_5`, `v2_5_1`, `v2_3_1` under `hl7apy/*/messages.py` and
`groups.py`) against every trigger-event XSD in this repo, **5 of the 6 flow schemas are byte-for-byte
equivalent to the official standard structure** for their HL7 version — they add nothing beyond what
`hl7apy` already enforces. Only **one** flow schema (`wds`'s `ADT_A05.xsd`) contains a genuine
customisation that deviates from the standard. There are also two concrete blockers that must be
fixed before `hl7apy` standard validation could safely take over: a version-support gap for `pims`,
and a parsing-mode bug in the existing `standard_validate.py` for group-structured messages (`A39`/`A40`).
Details below.

This library already implements both mechanisms, as complementary layers:

- [`validate.py`](hl7_validation/validate.py) — `validate_er7_with_flow_schema` (XSD-based, per flow)
- [`standard_validate.py`](hl7_validation/standard_validate.py) — `validate_er7_with_standard` (hl7apy-based, per HL7 version)

The [README](README.md) already documents them as intended to be used together: *"Both validation
methods can be used together — a message must pass both validations if both are configured."*

## 3. What each validator actually checks

| | Flow schema validation (XSD) | Standard validation (`hl7apy`) |
|---|---|---|
| Target | The specific message shape a **source system** actually sends (`phw`, `wds`, `pims`, `chemo`, `paris`) | The **generic official HL7 v2.x spec** for a version, independent of source system |
| Granularity | Custom cardinality, enumerations, patterns, fixed structures per flow | Segment presence/order/repetition and datatype component counts per the base standard |
| Source of truth | XSD files under `hl7_validation/resources/<flow>/` | `hl7apy`'s bundled structure definitions for the version |
| Extensible per source system? | Yes — arbitrary constraints via schema authoring | No — fixed to whatever `hl7apy` ships for that version |

## 4. Verified findings

### 4.1 Per-flow comparison: repo XSD vs. `hl7apy`'s official bundled structure

Method: installed `hl7apy==1.3.5` into a scratch venv and diffed each flow's trigger-event XSD
against the corresponding entry in `hl7apy/v2_*/messages.py` / `groups.py`.

| Flow | HL7 version | Structure(s) checked | Result |
|---|---|---|---|
| `chemo` | 2.4 | `ADT_A05` | ✅ Identical to `hl7apy` v2.4 (`PV1` mandatory, same segment sequence) |
| `paris` | 2.5.1 | `ADT_A05` | ✅ Identical to `hl7apy` v2.5.1 |
| `mosaiq` | 2.5 | `ADT_A05` | ✅ Identical to `hl7apy` v2.5 |
| `phw` | 2.5 | `ADT_A05`, `ADT_A39` | ✅ Identical to `hl7apy` v2.5 (`PV1` mandatory; `ADT_A39.PATIENT` repeating group matches `ADT_A39_PATIENT`) |
| `pims` | 2.3.1 | `ADT_A01`, `ADT_A40` | ✅ Identical to `hl7apy` v2.3.1 (`ADT_A40.PIDPD1MRGPV1` matches `ADT_A39_PATIENT` group exactly) |
| **`wds`** | 2.5 | `ADT_A05` | ❌ **Deviates** — wraps `PV1`/`PV2`/`ROL` in an **optional** `ADT_A05.VISIT` group, whereas the official v2.5 structure (and every other flow) requires `PV1` |

**Correction to the original draft of this report:** it previously characterised the `phw` vs `wds`
`PV1` difference as "both are legitimate flow-specific dialects." Having diffed against `hl7apy`'s
actual bundled structures, `phw` (and `chemo`, `paris`, `mosaiq`, `pims`) match the **official standard**
exactly. `wds` is the sole outlier with a real customisation.

This was confirmed functionally, not just by reading source: parsing a `wds`-style `ADT_A05` message
with no `PV1` under `hl7apy` `STRICT` validation raises `ValidationError: Missing required child
ADT_A05.PV1` — i.e. `hl7apy` standard validation would **reject valid WDS production messages** if
swapped in as-is.

### 4.2 Version coverage gap is a repo config limit, not an `hl7apy` limitation — corrected

The original draft claimed `hl7apy` doesn't support HL7 2.3.1 (used by `pims`). **That was wrong.**
`hl7apy==1.3.5` ships full structure/segment/field definitions for `v2_3_1` (confirmed:
`hl7apy/v2_3_1/messages.py` contains `ADT_A01`, `ADT_A39`, etc., and parses/validates a v2.3.1 `ADT_A01`
message correctly in testing). The actual restriction is self-imposed in this repo's
[`standard_validate.py`](hl7_validation/standard_validate.py):

```python
SUPPORTED_VERSIONS = frozenset({"2.4", "2.5", "2.5.1", "2.6"})
```

Adding `"2.3.1"` here is a one-line change (presumably gated on adding test coverage), not a library
constraint.

| Flow | HL7 base version | Supported by `hl7apy` itself | In this repo's `SUPPORTED_VERSIONS` |
|---|---|---|---|
| `chemo` | 2.4 | ✅ | ✅ |
| `phw` | 2.5 | ✅ | ✅ |
| `wds` | 2.5 | ✅ | ✅ |
| `paris` | 2.5.1 | ✅ | ✅ |
| `mosaiq` | 2.5 | ✅ | ✅ |
| `pims` | 2.3.1 | ✅ | ❌ (excluded today, fixable) |

### 4.3 New finding: `find_groups=False` breaks standard validation for merge messages (`A39`/`A40`)

`standard_validate.py` always calls `parse_message(..., find_groups=False)`. `ADT_A39`/`ADT_A40` are
**group-structured** messages — a repeating `(PID, [PD1], MRG, [PV1])` group, once per merged patient.
Tested empirically with a well-formed two-group merge message:

```text
find_groups=False → ChildNotValid: PID is not a valid child for <Message ADT_A39>   (rejects a VALID message)
find_groups=True  → VALID
```

This is an existing bug, independent of the XSD question: as written today, `validate_er7_with_standard`
/ `validate_parsed_message_with_standard` cannot correctly validate any real PHW/WDS/PIMS merge (`A39`/`A40`)
message — it would reject all of them. `find_groups=True` must be used for structures that define groups.

### 4.4 Real-world non-conformance (still a valid general concern)

Even though today's flows happen to mirror the standard almost exactly, XSDs remain the only mechanism
for encoding a deliberate future deviation (as `wds` already demonstrates) — e.g. a new source system
sending Z-segments, a tightened/loosened cardinality, or a fixed value set for a field. `hl7apy`'s
built-in rules are fixed per version and can't be parameterised per source system without forking or
patching the library's own structure definitions.

## 5. Recommendation

The claim holds for today's schemas, with conditions:

- `chemo`, `paris`, `mosaiq`, `phw`, and `pims` trigger-event XSDs are **not adding any constraint
  beyond the official standard** — they are functionally redundant with what `hl7apy` standard
  validation already enforces (once §4.2 and §4.3 are fixed: add `"2.3.1"` to `SUPPORTED_VERSIONS`,
  and use `find_groups=True` for group-structured messages).
- `wds`'s `ADT_A05` is the one flow that cannot be moved to `hl7apy` standard validation as-is — its
  optional-`PV1` customisation would be rejected by `hl7apy`'s `STRICT` validation. This flow would
  need either to keep its XSD, or have a small targeted post-processing step that tolerates the single
  known deviation (e.g. catching `ValidationError` on `ADT_A05.PV1` specifically and treating it as
  non-fatal for `wds` only).
- Keep the XSD mechanism available (not necessarily populated for every flow) for the day a genuinely
  custom deviation is needed again — removing it entirely would mean re-adding an XSD engine later
  rather than just an XSD file.

Net: migrating `chemo`, `paris`, `mosaiq`, `phw`, and `pims` to `hl7apy`-only validation is technically
sound and would remove real, verified duplication (see also `xsd_dup.md`). `wds` should keep bespoke
handling for its one deviation.

## 6. Related follow-up (not addressed here)

[`xsd_dup.md`](xsd_dup.md) separately notes that base HL7 version schemas (`2_5_fields.xsd`,
`2_5_segments.xsd`, `2_5_types.xsd`) are byte-identical duplicates between `phw` and `wds` today, and
that this duplication is structural (recurs for any new flow sharing an existing HL7 version). That is
a schema-organisation concern, distinct from the hl7apy-vs-XSD question addressed above, and is
already tracked in `xsd_dup.md`.
