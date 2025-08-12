from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from typing import Dict, List


@dataclass(frozen=True)
class SchemaDefinition:
    name: str
    resource_filename: str


_SCHEMAS: Dict[str, SchemaDefinition] = {
    "phw_schema": SchemaDefinition(
        name="phw_schema",
        resource_filename="phw_schema.xsd",
    ),
}


def list_available_schemas() -> List[str]:
    return sorted(_SCHEMAS.keys())


def get_schema_xsd_path(schema_name: str) -> str:
    schema = _SCHEMAS.get(schema_name)
    if schema is None:
        available = ", ".join(list_available_schemas())
        raise ValueError(f"Unknown schema '{schema_name}'. Available: {available}")
    # Resolve the on-disk path of the packaged XSD file
    return str(files("hl7_validation.resources") / schema.resource_filename)


