"""Sample RISP-style ADT messages used across hl7_core_reference_transformer tests.

PID field layout (v2.5) relevant to this transformer:
  PID-5.5  Title (XPN.5, simple sub-component)
  PID-8    Sex (simple field)
  PID-15.1 Language (CE.1)
  PID-16.1 Marital Status (CE.1)
  PID-17.1 Religion (CE.1)
  PID-22.1 Ethnicity (CE.1)
"""
from __future__ import annotations


def _build_message(msh_9: str, pid_fields: dict[int, str]) -> str:
    """Build a minimal ADT message from an MSH-9 value and a {field_number: value} PID field map."""
    max_field = max(pid_fields)
    fields = ["PID"] + [pid_fields.get(i, "") for i in range(1, max_field + 1)]
    pid_segment = "|".join(fields)
    return (
        f"MSH|^~\\&|349|349|100|100|20250624162400||{msh_9}|123456789|P|2.5|||NE|NE\r"
        f"{pid_segment}\r"
    )


# A28 message with all six in-scope fields populated.
A28_ALL_FIELDS_POPULATED = _build_message(
    "ADT^A28",
    {
        1: "1",
        2: "1000000001^^^^NH",
        3: "1000000001^^^^NH",
        5: "TEST^TEST^^^Mr.",
        7: "20000101000000",
        8: "1",
        15: "EN^English",
        16: "11^Single",
        17: "22^SomeReligion",
        22: "33^SomeEthnicity",
    },
)

# A31 message with all six in-scope fields empty/absent.
A31_ALL_FIELDS_EMPTY = _build_message(
    "ADT^A31",
    {
        1: "1",
        2: "1000000001^^^^NH",
        3: "1000000001^^^^NH",
        5: "TEST^TEST",
        7: "20000101000000",
    },
)

# A40 message with the literal HL7 "null value" ("") in PID-8 (Sex) — must be left untouched.
A40_SEX_HL7_NULL = _build_message(
    "ADT^A40",
    {
        1: "1",
        3: "1000000001^^^^NH",
        5: "TEST^TEST",
        8: '""',
    },
)

# A message type this transformer is not responsible for — must pass through unchanged.
A04_NOT_IN_SCOPE = _build_message(
    "ADT^A04",
    {
        1: "1",
        3: "1000000001^^^^NH",
        5: "TEST^TEST",
        8: "1",
    },
)

# No PID segment at all — must not raise.
MSH_ONLY_NO_PID = "MSH|^~\\&|349|349|100|100|20250624162400||ADT^A28|123456789|P|2.5|||NE|NE\r"
