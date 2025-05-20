from dataclasses import dataclass
from pathlib import Path

from xmlschema import XMLSchema


@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    errors: list[str]


class XmlValidator:
    def __init__(self) -> None:
        self.schema_path = Path(__file__).parent / "WPAS_Schema.xsd"
        self.schema = XMLSchema(self.schema_path)

    def validate(self, xml: str) -> ValidationResult:
        errors = list(map(lambda e: e.reason or "", self.schema.iter_errors(xml)))
        is_valid = len(errors) <= 0
        return ValidationResult(is_valid=is_valid, errors = errors)
