from dataclasses import dataclass
from functools import lru_cache

import xmlschema

from .convert import er7_to_hl7v2xml
from .schemas import get_schema_xsd_path_for
from .utils.message_utils import (
    extract_message_structure,
    extract_message_trigger,
    extract_message_type,
    parse_er7_message,
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


def validate_er7_with_flow(er7_string: str, flow_name: str) -> None:
    try:
        msg = parse_er7_message(er7_string, find_groups=False)
    except Exception:
        raise XmlValidationError(PARSE_ERROR_MSG)

    structure = extract_message_structure(msg)
    trigger = extract_message_trigger(msg)
    msg_type = extract_message_type(msg)

    def _map_trigger_to_structure_id(message_type: str, trig: str) -> str | None:
        mapping: dict[tuple[str, str], str] = {
            ("ADT", "A28"): "ADT_A05",
            ("ADT", "A31"): "ADT_A05",
            ("ADT", "A40"): "ADT_A39",
        }
        return mapping.get((message_type, trig))

    if structure:
        structure_id = structure
        override_structure = None
    elif trigger:
        if msg_type:
            mapped = _map_trigger_to_structure_id(msg_type, trigger)
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
