from dataclasses import dataclass
from functools import lru_cache

import xmlschema

from .convert import er7_to_hl7v2xml, STRUCTURE_ERROR_MSG
from .schemas import get_schema_xsd_path_for, get_fallback_structure_for
from .utils.message_utils import (
    parse_er7_message,
    extract_message_structure,
    extract_message_trigger,
    extract_message_type,
)

PARSE_ERROR_MSG = "Unable to parse ER7 message"


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
        msg = parse_er7_message(er7_string, find_groups=False)
    except Exception:
        raise XmlValidationError(STRUCTURE_ERROR_MSG)

    structure = extract_message_structure(msg)
    if not structure:
        raise XmlValidationError(STRUCTURE_ERROR_MSG)

    parts = structure.split("_")
    suffix = parts[-1] if parts else ""
    if not suffix:
        raise XmlValidationError(STRUCTURE_ERROR_MSG)
    return suffix


def validate_er7_with_flow(er7_string: str, flow_name: str) -> None:
    try:
        msg = parse_er7_message(er7_string, find_groups=False)
    except Exception:
        raise XmlValidationError(PARSE_ERROR_MSG)

    structure = extract_message_structure(msg)
    trigger = extract_message_trigger(msg)
    msg_type = extract_message_type(msg)

    structure_or_trigger: str
    override_structure: str | None = None

    if structure:
        parts = structure.split("_")
        suffix = parts[-1] if parts else ""
        if not suffix:
            raise XmlValidationError(STRUCTURE_ERROR_MSG)
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
