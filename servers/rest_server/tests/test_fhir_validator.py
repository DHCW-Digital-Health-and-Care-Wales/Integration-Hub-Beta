"""Tests for the FHIR resource validator (spike INTHUB-590477)."""
import json
import unittest

from rest_server.errors import ValidationError
from rest_server.validators.fhir_validator import FhirResourceValidator

VALID_BUNDLE = json.dumps(
    {
        "resourceType": "Bundle",
        "type": "message",
        "entry": [],
    }
)

INVALID_BUNDLE_WRONG_TYPE_FIELD = json.dumps(
    {
        "resourceType": "Bundle",
        "type": 12345,  # Bundle.type must be a string code, not a number.
        "entry": [],
    }
)


class TestFhirResourceValidator(unittest.TestCase):
    def test_valid_bundle_passes(self) -> None:
        validator = FhirResourceValidator(allowed_resource_types=["Bundle"])
        validator.validate(VALID_BUNDLE, "Bundle")

    def test_disallowed_resource_type_raises(self) -> None:
        validator = FhirResourceValidator(allowed_resource_types=["Bundle"])
        with self.assertRaises(ValidationError):
            validator.validate(VALID_BUNDLE, "Patient")

    def test_structurally_invalid_resource_raises(self) -> None:
        validator = FhirResourceValidator(allowed_resource_types=["Bundle"])
        with self.assertRaises(ValidationError):
            validator.validate(INVALID_BUNDLE_WRONG_TYPE_FIELD, "Bundle")

    def test_unsupported_configured_resource_type_raises(self) -> None:
        with self.assertRaises(ValueError):
            FhirResourceValidator(allowed_resource_types=["Patient"])

    def test_empty_allowed_resource_types_raises(self) -> None:
        with self.assertRaises(ValueError):
            FhirResourceValidator(allowed_resource_types=[])


if __name__ == "__main__":
    unittest.main()
