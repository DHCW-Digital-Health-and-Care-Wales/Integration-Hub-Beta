from dataclasses import dataclass
from functools import lru_cache

import xmlschema
from hl7apy.parser import parse_message

from .convert import er7_to_hl7v2xml
from .schemas import get_schema_xsd_path_for, get_fallback_structure_for


@dataclass
class XmlValidationError(Exception):
    message: str

    def __str__(self) -> str:
        return self.message


@lru_cache(maxsize=16)
def _get_compiled_schema(xsd_path: str) -> xmlschema.XMLSchema:
    return xmlschema.XMLSchema(xsd_path)


def validate_xml(xml_string: str, xsd_path: str) -> None:
    try:
        schema = _get_compiled_schema(xsd_path)
        schema.validate(xml_string)
    except xmlschema.validators.exceptions.XMLSchemaValidationError as e:  # type: ignore[attr-defined]
        raise XmlValidationError(str(e))


def _extract_trigger_event_from_er7(er7_string: str) -> str:
    try:
        msg = parse_message(er7_string, find_groups=False)
    except Exception:
        raise XmlValidationError(
            "Unable to determine structure (MSH-9.3) from ER7 message"
        )

    structure_value = getattr(msg.msh.msh_9.msh_9_3, "value", None)  # type: ignore[attr-defined]
    if not structure_value:
        raise XmlValidationError(
            "Unable to determine structure (MSH-9.3) from ER7 message"
        )

    parts = str(structure_value).split("_")
    suffix = parts[-1] if parts else ""
    if not suffix:
        raise XmlValidationError(
            "Unable to determine structure (MSH-9.3) from ER7 message"
        )
    return suffix


def validate_er7_with_flow(er7_string: str, flow_name: str) -> None:
    try:
        msg = parse_message(er7_string, find_groups=False)
        structure_value = getattr(msg.msh.msh_9.msh_9_3, "value", None)  # type: ignore[attr-defined]
        trigger_value = getattr(msg.msh.msh_9.msh_9_2, "value", None)  # type: ignore[attr-defined]
        msg_type_value = getattr(msg.msh.msh_9.msh_9_1, "value", None)  # type: ignore[attr-defined]
    except Exception:
        raise XmlValidationError("Unable to parse ER7 message")
    
    structure = str(structure_value).strip() if structure_value else ""
    trigger = str(trigger_value).strip() if trigger_value else ""
    msg_type = str(msg_type_value).strip() if msg_type_value else ""
    
    structure_or_trigger: str
    override_structure: str | None = None
    
    if structure:
        parts = structure.split("_")
        suffix = parts[-1] if parts else ""
        if not suffix:
            raise XmlValidationError("Unable to determine structure (MSH-9.3) from ER7 message")
        structure_or_trigger = suffix
    elif trigger:
        fallback = get_fallback_structure_for(flow_name, trigger)
        if not fallback:
            raise XmlValidationError(
                f"No fallback structure configured for flow '{flow_name}' and trigger '{trigger}' when MSH-9.3 is missing"
            )
        structure_or_trigger = fallback
        override_structure = f"{msg_type}_{fallback}" if msg_type else None
    else:
        raise XmlValidationError("Unable to determine structure or trigger from ER7 message")
    
    xsd_path = get_schema_xsd_path_for(flow_name, structure_or_trigger)
    xml_string = er7_to_hl7v2xml(
        er7_string, structure_xsd_path=xsd_path, override_structure_id=override_structure
    )
    validate_xml(xml_string, xsd_path)
