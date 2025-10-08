Field Utils Lib

Shared utilities for safely reading and setting nested HL7 fields using hl7apy.

- Supports dot-separated paths like `pid_5.xpn_1.fn_1`
- Supports single-repetition bracket notation like `pid_13[1].xtn_1`

Exported functions:
- `get_hl7_field_value(hl7_segment, field_path) -> str`
- `set_nested_field(source_obj, target_obj, field_path) -> bool`

