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
    trigger_event = _extract_trigger_event_from_er7(er7_string)
    xsd_path = get_schema_xsd_path_for(flow_name, trigger_event)
    xml_string = er7_to_hl7v2xml(er7_string, structure_xsd_path=xsd_path)
    validate_xml(xml_string, xsd_path)
