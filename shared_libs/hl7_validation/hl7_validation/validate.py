from dataclasses import dataclass

import xmlschema

from .schemas import get_schema_xsd_path


@dataclass
class XmlValidationError(Exception):
    message: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.message


def validate_xml(xml_string: str, xsd_path: str) -> None:
    try:
        schema = xmlschema.XMLSchema(xsd_path)
        schema.validate(xml_string)
    except xmlschema.validators.exceptions.XMLSchemaValidationError as e:  # type: ignore[attr-defined]
        raise XmlValidationError(str(e))


def validate_xml_with_schema(xml_string: str, schema_name: str) -> None:

    xsd_path = get_schema_xsd_path(schema_name)
    validate_xml(xml_string, xsd_path)


