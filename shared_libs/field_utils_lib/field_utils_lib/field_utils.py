from typing import Any

from hl7apy.exceptions import ChildNotFound


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
    Supports single-repetition bracket notation, e.g. pid_13[1].xtn_1
    """
    current_element = hl7_segment
    for field_name in field_path.split("."):
        try:
            if "[" in field_name and field_name.endswith("]"):
                field_base, index_part = field_name.split("[", 1)
                index = int(index_part.rstrip("]"))
                field_array = getattr(current_element, field_base)
                if hasattr(field_array, "__getitem__") and len(field_array) > index:
                    current_element = field_array[index]
                else:
                    return ""
            else:
                current_element = getattr(current_element, field_name)
            if not current_element:
                return ""
        except (AttributeError, IndexError, ChildNotFound, ValueError):
            return ""

# Assuming all hl7apy fields have a .value - see docs https://crs4.github.io/hl7apy/api_docs/core.html
    if current_element is not None:
        field_value = current_element.value
         # Handle nested values - HL7 datatype objects may have their own .value attribute
        if hasattr(field_value, "value"):
            field_value = field_value.value
        return str(field_value) if field_value is not None else ""
    return ""


def set_nested_field(source_obj: Any, target_obj: Any, field_path: str) -> bool:
    """
    Copy a nested field from source to target using a dot-separated path.
    Only sets the target field if the source field exists and has a value.
    Example usage:
    - set_nested_field(original_msh, new_message.msh, "msh_7.ts_1") - nested field
    - set_nested_field(original_msh, new_message.msh, "msh_8")      - top-level field

    If a subfield is missing for example xad_1 from pid_11, any children of this subfield will be set to empty string.
    Example usage:
     - set_nested_field(original_msh, new_message.msh, "pid_11.xad_1.sad_1")  - sad_1 will be set to ""
    """
    fields = field_path.split(".")

    try:
        current_source = source_obj
        for field_name in fields[:-1]:
            if not _safe_hasattr(current_source, field_name):
                return False
            current_source = getattr(current_source, field_name)

        final_field_name = fields[-1]
        if not _safe_hasattr(current_source, final_field_name):
            return False

        final_field_value = getattr(current_source, final_field_name)
        field_content = (
            getattr(final_field_value, "value", final_field_value)
            if hasattr(final_field_value, "value")
            else final_field_value
        )
        if not field_content:
            return False

        current_target = target_obj
        for field_name in fields[:-1]:
            current_target = getattr(current_target, field_name)

        setattr(current_target, final_field_name, final_field_value)
        return True
    except (AttributeError, IndexError, ChildNotFound):
        return False


def _safe_hasattr(obj: Any, name: str) -> bool:
    """
    Helper function to safely check if an object has an attribute,
    handling hl7apy's ChildNotFound exceptions.
    """
    try:
        getattr(obj, name)
        return True
    except (AttributeError, IndexError, ChildNotFound):
        return False


