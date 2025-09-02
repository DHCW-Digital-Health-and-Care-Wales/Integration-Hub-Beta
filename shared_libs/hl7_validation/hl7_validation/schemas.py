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


def _resolve_mapping_for_key(triggers: Dict[str, str], key: str) -> str | None:
    return triggers.get(key)
