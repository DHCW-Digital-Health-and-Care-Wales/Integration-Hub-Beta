from __future__ import annotations

from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Dict, List


@lru_cache(maxsize=1)
def list_schema_groups() -> List[str]:
    groups: List[str] = []
    res_root = files("hl7_validation.resources")
    try:
        for item in res_root.iterdir():
            if item.is_dir():
                groups.append(item.name)
    except (OSError, AttributeError):
        pass
    return sorted(set(groups))


@lru_cache(maxsize=64)
def list_schemas_for_group(flow_name: str) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    flow_dir = files("hl7_validation.resources") / flow_name
    try:
        for item in flow_dir.iterdir():
            if item.name.lower().endswith(".xsd"):
                trigger = Path(item.name).stem
                mapping.setdefault(trigger, f"{flow_name}/{item.name}")
    except (FileNotFoundError, NotADirectoryError, PermissionError, OSError):
        return {}
    return mapping


def get_schema_xsd_path_for(flow_name: str, trigger_event_or_structure: str) -> str:
    triggers = list_schemas_for_group(flow_name)
    from_key = _resolve_mapping_for_key(triggers, trigger_event_or_structure)
    if not from_key:
        available = ", ".join(sorted(triggers.keys())) or "<none>"
        raise ValueError(
            f"No XSD mapping for flow '{flow_name}' and "
            f"trigger/structure '{trigger_event_or_structure}'. "
            f"Available: {available}"
        )
    return str(files("hl7_validation.resources") / from_key)


@lru_cache(maxsize=64)
def list_schemas_for_schema_dir(schema_dir_name: str) -> Dict[str, str]:
    """
    Same behavior as ``list_schemas_for_group``, but named/scoped for schema directories that
    are keyed by message structure (+ version) rather than by flow — e.g. ``"ORU_R01"``,
    ``"OMG_O19"``. These directories are shared across multiple flows that validate the same
    message structure, so they must not be duplicated per-flow.
    """
    mapping: Dict[str, str] = {}
    schema_dir = files("hl7_validation.resources") / schema_dir_name
    try:
        for item in schema_dir.iterdir():
            if item.name.lower().endswith(".xsd"):
                trigger = Path(item.name).stem
                mapping.setdefault(trigger, f"{schema_dir_name}/{item.name}")
    except (FileNotFoundError, NotADirectoryError, PermissionError, OSError):
        return {}
    return mapping


def get_schema_xsd_path_for_structure(schema_dir_name: str, schema_file_name: str) -> str:
    """
    Resolve an XSD path from a schema directory named after the message structure (+ version),
    instead of a per-flow directory. See ``get_schema_xsd_path_for`` for the flow-based
    equivalent.
    """
    triggers = list_schemas_for_schema_dir(schema_dir_name)
    from_key = _resolve_mapping_for_key(triggers, schema_file_name)
    if not from_key:
        available = ", ".join(sorted(triggers.keys())) or "<none>"
        raise ValueError(
            f"No XSD mapping for schema directory '{schema_dir_name}' and "
            f"schema file '{schema_file_name}'. "
            f"Available: {available}"
        )
    return str(files("hl7_validation.resources") / from_key)


def _resolve_mapping_for_key(triggers: Dict[str, str], key: str) -> str | None:
    return triggers.get(key)
