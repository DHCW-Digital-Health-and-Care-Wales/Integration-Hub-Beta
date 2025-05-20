from dataclasses import dataclass
from pathlib import Path

import xmlschema


@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    errors: list[str]


class XmlValidator:
    def __init__(self):
        self.schema_path = Path(__file__).parent / "WPAS_Schema.xsd"
        self.get_validator()

    def get_validator(self):
        self.schema = xmlschema.XMLSchema(self.schema_path)

    def validate(self, xml: str) -> ValidationResult:
        errors = list(map(lambda e: e.reason, self.schema.iter_errors(xml)))
        is_valid = len(errors) <= 0
        return ValidationResult(is_valid=is_valid, errors=errors)
