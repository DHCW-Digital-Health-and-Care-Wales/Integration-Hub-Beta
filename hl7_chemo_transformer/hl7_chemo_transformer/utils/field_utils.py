from typing import Any, Optional


def get_hl7_field_value(hl7_segment: Any, field_path: str) -> str:
    """
    Safely retrieves the string value of a nested HL7 field using a dot-separated path.

    Traverses the HL7 segment hierarchy following the provided path,
    handling missing attributes and empty values gracefully (returns empty string to maintain compatibility with hl7apy)
    Works with hl7apy objects which may have .value attributes or can be converted to strings.
    Example usage:
    - get_hl7_field_value(original_msh, "msh_4.hd_1") = "HOSPITAL NAME"
    - get_hl7_field_value(original_pid, "pid_5.xpn_1.fn_1") = "TEST"
    - get_hl7_field_value(original_msh, "nonexistent.field") = ""
    """
    current_element = hl7_segment
    # Loop through each attribute in the field path in order
    for field_name in field_path.split("."):
        try:
            current_element = getattr(current_element, field_name)
            if not current_element:
                return ""  # Empty field
        except (AttributeError, IndexError):
            return ""  # Non-existent field

    # Assuming all hl7apy fields have a .value - see docs https://crs4.github.io/hl7apy/api_docs/core.html
    if current_element is not None:
        field_value = current_element.value
        return str(field_value) if field_value is not None else ""
    return ""


def set_nested_field(source_msg: Any, target_msg: Any, field: str, subfield: Optional[str] = None) -> None:
    """
    Safely copy a field or nested field (e.g., msh_7.ts_1) from source to target message.
    Only copies if the source field (and subfield, if provided) exist and are populated.
    Example usage:
    - set_nested_field(original_msh, new_message.msh, "msh_7", "ts_1") - nested field
    - set_nested_field(original_msh, new_message.msh, "msh_8")         - top-level field
    """
    if hasattr(source_msg, field):
        src_field = getattr(source_msg, field)
        if src_field:
            if subfield:
                if hasattr(src_field, subfield):
                    value = getattr(src_field, subfield)
                    if value:
                        setattr(getattr(target_msg, field), subfield, value)
            else:
                setattr(target_msg, field, src_field)
