from dataclasses import dataclass
from functools import lru_cache

import xmlschema
from hl7apy.core import Message

from .constants import PARSE_ERROR_MSG
from .convert import er7_to_hl7v2xml
from .schemas import get_schema_xsd_path_for
from .utils.message_utils import (
    extract_message_structure,
    extract_message_trigger,
    extract_message_type,
    parse_er7_message,
)

_TRIGGER_MAPPING: dict[tuple[str, str], str] = {
    ("ADT", "A28"): "ADT_A05",
    ("ADT", "A31"): "ADT_A05",
    ("ADT", "A40"): "ADT_A39",
}


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


def validate_er7_with_flow(er7_string: str, flow_name: str) -> None:
    try:
        msg = parse_er7_message(er7_string, find_groups=False)
    except Exception:
        raise XmlValidationError(PARSE_ERROR_MSG)

    _validate_flow_logic(msg, er7_string, flow_name)


def validate_parsed_message_with_flow(msg: Message, er7_string: str, flow_name: str) -> None:
    """
    Validate already-parsed HL7 message against flow-specific XSD schema.

    Optimized version that accepts pre-parsed message to avoid redundant parsing.

    Args:
        msg: Already parsed HL7 message object
        er7_string: Original ER7 string (needed for XML conversion)
        flow_name: Flow identifier for schema selection

    Raises:
        XmlValidationError: If validation fails
    """
    _validate_flow_logic(msg, er7_string, flow_name)


def _validate_flow_logic(msg: Message, er7_string: str, flow_name: str) -> None:
    structure = extract_message_structure(msg)
    trigger = extract_message_trigger(msg)
    msg_type = extract_message_type(msg)

    if structure:
        structure_id = structure
        override_structure = None
    elif trigger:
        if msg_type:
            mapped = _TRIGGER_MAPPING.get((msg_type, trigger))
            structure_id = mapped or f"{msg_type}_{trigger}"
        else:
            structure_id = trigger
        override_structure = structure_id
    else:
        raise XmlValidationError("Unable to determine structure or trigger from ER7 message")

    xsd_path = get_schema_xsd_path_for(flow_name, structure_id)
    xml_string = er7_to_hl7v2xml(
        er7_string, structure_xsd_path=xsd_path, override_structure_id=override_structure
    )
    validate_xml(xml_string, xsd_path)
