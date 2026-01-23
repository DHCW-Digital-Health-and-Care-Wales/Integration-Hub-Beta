from dataclasses import dataclass
from functools import lru_cache
from typing import Optional, Tuple

import xmlschema
from hl7apy.core import Message

from .constants import PARSE_ERROR_MSG
from .convert import er7_to_hl7v2xml
from .schemas import get_schema_xsd_path_for
from .utils.message_utils import (
    extract_message_structure,
    extract_message_trigger,
    extract_message_type,
    get_message_field_value,
    parse_er7_message,
)
from .validation_result import ValidationResult

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


def validate_er7_with_flow_schema(er7_string: str, flow_name: str) -> None:
    try:
        msg = parse_er7_message(er7_string, find_groups=False)
    except Exception:
        raise XmlValidationError(PARSE_ERROR_MSG)

    _validate_flow_schema_logic(msg, er7_string, flow_name)


def validate_parsed_message_with_flow_schema(msg: Message, er7_string: str, flow_name: str) -> None:
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
    _validate_flow_schema_logic(msg, er7_string, flow_name)


def _validate_flow_schema_logic(msg: Message, er7_string: str, flow_name: str) -> None:
    structure = extract_message_structure(msg)
    trigger = extract_message_trigger(msg)
    msg_type = extract_message_type(msg)

    if structure:
        structure_id = structure
        override_structure = None
    elif trigger:
        if msg_type:
            structure_id = _TRIGGER_MAPPING.get((msg_type, trigger), f"{msg_type}_{trigger}")
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


def _resolve_structure_info(
    msg: Message,
) -> Tuple[str, Optional[str], str, str]:
    """
    Extract and resolve structure information from parsed message.

    Returns:
        Tuple of (structure_id, override_structure, message_type, trigger_event)
    """
    structure = extract_message_structure(msg)
    trigger = extract_message_trigger(msg)
    msg_type = extract_message_type(msg)

    if structure:
        structure_id = structure
        override_structure = None
    elif trigger:
        if msg_type:
            structure_id = _TRIGGER_MAPPING.get((msg_type, trigger), f"{msg_type}_{trigger}")
        else:
            structure_id = trigger
        override_structure = structure_id
    else:
        raise XmlValidationError("Unable to determine structure or trigger from ER7 message")

    return structure_id, override_structure, msg_type, trigger


def _extract_message_control_id(msg: Message) -> Optional[str]:
    """Extract MSH-10 message control ID from parsed message."""
    return get_message_field_value(msg, "msh.msh_10")


def validate_and_convert_er7_with_flow_schema(er7_string: str, flow_name: str) -> ValidationResult:
    """
    Validate ER7 message against flow-specific XSD schema and return the XML.

    This function validates the message and returns both the validation status
    and the generated XML, allowing the XML to be stored in a database without
    requiring a separate conversion step.

    Args:
        er7_string: The HL7 message in ER7 format
        flow_name: Flow identifier for schema selection

    Returns:
        ValidationResult containing the generated XML and validation status

    Raises:
        XmlValidationError: If parsing fails (not schema validation - that's captured in result)
    """
    try:
        msg = parse_er7_message(er7_string, find_groups=False)
    except Exception:
        raise XmlValidationError(PARSE_ERROR_MSG)

    return validate_and_convert_parsed_message_with_flow_schema(msg, er7_string, flow_name)


def validate_and_convert_parsed_message_with_flow_schema(
    msg: Message, er7_string: str, flow_name: str
) -> ValidationResult:
    """
    Validate pre-parsed HL7 message against flow-specific XSD schema and return XML.

    Optimized version that accepts pre-parsed message to avoid redundant parsing.
    Returns both the validation status and the generated XML for database storage.

    Args:
        msg: Already parsed HL7 message object
        er7_string: Original ER7 string (needed for XML conversion)
        flow_name: Flow identifier for schema selection

    Returns:
        ValidationResult containing the generated XML and validation status
    """
    structure_id, override_structure, msg_type, trigger = _resolve_structure_info(msg)
    message_control_id = _extract_message_control_id(msg)

    xsd_path = get_schema_xsd_path_for(flow_name, structure_id)
    xml_string = er7_to_hl7v2xml(
        er7_string, structure_xsd_path=xsd_path, override_structure_id=override_structure
    )

    try:
        validate_xml(xml_string, xsd_path)
        return ValidationResult(
            xml_string=xml_string,
            structure_id=structure_id,
            message_type=msg_type,
            trigger_event=trigger,
            message_control_id=message_control_id,
            is_valid=True,
            error_message=None,
        )
    except XmlValidationError as e:
        return ValidationResult(
            xml_string=xml_string,
            structure_id=structure_id,
            message_type=msg_type,
            trigger_event=trigger,
            message_control_id=message_control_id,
            is_valid=False,
            error_message=str(e),
        )


def convert_er7_to_xml_with_flow_schema(er7_string: str, flow_name: str) -> str:
    """
    Convert ER7 message to XML using flow-specific schema without validation.

    Use this when you only need the XML conversion without schema validation,
    for example when validation was already performed separately.

    Args:
        er7_string: The HL7 message in ER7 format
        flow_name: Flow identifier for schema selection

    Returns:
        The HL7v2 XML string representation of the message

    Raises:
        XmlValidationError: If parsing or structure resolution fails
    """
    try:
        msg = parse_er7_message(er7_string, find_groups=False)
    except Exception:
        raise XmlValidationError(PARSE_ERROR_MSG)

    structure_id, override_structure, _, _ = _resolve_structure_info(msg)
    xsd_path = get_schema_xsd_path_for(flow_name, structure_id)

    return er7_to_hl7v2xml(
        er7_string, structure_xsd_path=xsd_path, override_structure_id=override_structure
    )
