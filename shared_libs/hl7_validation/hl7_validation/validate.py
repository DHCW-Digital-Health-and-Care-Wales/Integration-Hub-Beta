from dataclasses import dataclass

import xmlschema


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


