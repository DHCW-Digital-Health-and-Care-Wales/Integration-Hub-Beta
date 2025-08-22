from typing import Optional, Any
from hl7apy.parser import parse_message


def get_message_field_value(msg: Any, field_path: str, default: Optional[str] = None) -> Optional[str]:
    try:
        parts: list[str] = field_path.split('.')
        current: Any = msg
        for part in parts:
            current = getattr(current, part, None)
            if current is None:
                return default
        return getattr(current, 'value', default) if current else default
    except (AttributeError, TypeError):
        return default


def extract_message_structure(msg: Any) -> str:
    structure_value = get_message_field_value(msg, "msh.msh_9.msh_9_3")
    return str(structure_value).strip() if structure_value else ""


def extract_message_trigger(msg: Any) -> str:
    trigger_value = get_message_field_value(msg, "msh.msh_9.msh_9_2")
    return str(trigger_value).strip() if trigger_value else ""


def extract_message_type(msg: Any) -> str:
    type_value = get_message_field_value(msg, "msh.msh_9.msh_9_1")
    return str(type_value).strip() if type_value else ""


def extract_msh7_datetime(msg: Any) -> str:
    datetime_value = get_message_field_value(msg, "msh.msh_7")
    return str(datetime_value).strip() if datetime_value else ""


def parse_er7_message(er7_string: str, find_groups: bool = False) -> Any:
    return parse_message(er7_string, find_groups=find_groups)
