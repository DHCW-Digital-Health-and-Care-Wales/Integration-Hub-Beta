from dataclasses import dataclass
from functools import lru_cache

import xmlschema
from hl7apy.parser import parse_message

from .convert import er7_to_hl7v2xml
from .schemas import get_schema_xsd_path_for


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
        trigger = msg.msh.msh_9.msh_9_2.value
        if trigger:
            return trigger
    except Exception:
        pass

    try:
        first_segment = er7_string.split("\r", 1)[0]
        fields = first_segment.split("|")
        comp = fields[8].split("^")
        if len(comp) >= 2 and comp[1]:
            return comp[1]
    except Exception:
        pass
    raise XmlValidationError("Unable to determine trigger event (MSH-9.2) from ER7 message")


def validate_er7_with_flow(er7_string: str, flow_name: str) -> None:
    trigger_event = _extract_trigger_event_from_er7(er7_string)
    xsd_path = get_schema_xsd_path_for(flow_name, trigger_event)
    # Provide the structure XSD path to the converter so it can infer grouping dynamically
    xml_string = er7_to_hl7v2xml(er7_string, structure_xsd_path=xsd_path)
    validate_xml(xml_string, xsd_path)

