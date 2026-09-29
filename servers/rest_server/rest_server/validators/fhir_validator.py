"""Validates a payload as a structurally-conformant FHIR R4B resource.

SPIKE (INTHUB-590477): structural/cardinality validation only, via the ``fhir.resources`` models
(already a dependency of ``transformers/xml_fhir_proms_transformer``). This does NOT validate
against custom StructureDefinitions/profiles or terminology bindings (ValueSet/CodeSystem) - see
the spike findings for follow-up options (FHIRPath invariants, terminology server integration).
"""
from __future__ import annotations

from typing import Dict, Type

from fhir.resources.R4B.bundle import Bundle
from fhir.resources.R4B.resource import Resource
from pydantic import ValidationError as PydanticValidationError

from rest_server.errors import ValidationError

# Extend as additional resource types need to be accepted directly (not just inside a Bundle).
_RESOURCE_MODELS: Dict[str, Type[Resource]] = {
    "Bundle": Bundle,
}


class FhirResourceValidator:
    def __init__(self, allowed_resource_types: list[str]) -> None:
        if not allowed_resource_types:
            raise ValueError("allowed_resource_types must not be empty")

        unsupported = set(allowed_resource_types) - _RESOURCE_MODELS.keys()
        if unsupported:
            raise ValueError(
                f"Unsupported FHIR resource type(s) in FHIR_ALLOWED_RESOURCE_TYPES: {', '.join(sorted(unsupported))}. "
                f"Supported: {', '.join(sorted(_RESOURCE_MODELS))}"
            )

        self.allowed_resource_types = set(allowed_resource_types)

    def validate(self, payload_json: str, structure_id: str | None) -> None:
        if structure_id not in self.allowed_resource_types:
            raise ValidationError(
                f"Unsupported or disallowed resourceType '{structure_id}'. "
                f"Allowed: {', '.join(sorted(self.allowed_resource_types))}"
            )

        model = _RESOURCE_MODELS[structure_id]
        try:
            model.model_validate_json(payload_json)
        except PydanticValidationError as exc:
            raise ValidationError(f"FHIR resource validation failed: {exc}") from exc
