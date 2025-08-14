from __future__ import annotations

from functools import lru_cache
from importlib.resources import files
from typing import Dict, List, Optional
import json


@lru_cache(maxsize=1)
def list_schema_groups() -> List[str]:
    groups: List[str] = []
    res_root = files("hl7_validation.resources")
    for item in getattr(res_root, "iterdir", lambda: [])():  # type: ignore[attr-defined]
        try:
            if item.is_dir():
                groups.append(item.name)
        except (OSError, AttributeError):
            continue
    return sorted(set(groups))


@lru_cache(maxsize=64)
def list_schemas_for_group(flow_name: str) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    flow_dir = files("hl7_validation.resources") / flow_name
    try:
        for item in getattr(flow_dir, "iterdir", lambda: [])():  # type: ignore[attr-defined]
            try:
                if item.name.lower().endswith(".xsd"):
                    trigger = item.stem
                    mapping.setdefault(trigger, f"{flow_name}/{item.name}")
            except (OSError, AttributeError):
                continue
    except (FileNotFoundError, NotADirectoryError, PermissionError):
        return {}
    return mapping


def get_schema_xsd_path_for(flow_name: str, trigger_event: str) -> str:
    triggers = list_schemas_for_group(flow_name)
    xsd_rel = triggers.get(trigger_event)
    if not xsd_rel:
        available = ", ".join(sorted(triggers.keys())) or "<none>"
        raise ValueError(
            f"No XSD mapping for flow '{flow_name}' and trigger '{trigger_event}'. Available triggers: {available}"
        )
    return str(files("hl7_validation.resources") / xsd_rel)


@lru_cache(maxsize=1)
def _load_fallback_mappings() -> Dict[str, Dict[str, str]]:
    cfg_path = files("hl7_validation.resources") / "structure_fallbacks.json"
    try:
        with cfg_path.open("r", encoding="utf-8") as f:  # type: ignore[attr-defined]
            data = json.load(f)
    except (OSError, FileNotFoundError, IsADirectoryError, PermissionError):
        return {}
    if not isinstance(data, dict):
        return {}
    result: Dict[str, Dict[str, str]] = {}
    for flow, mapping in data.items():
        if isinstance(mapping, dict):
            result[str(flow)] = {str(k): str(v) for k, v in mapping.items()}
    return result


def get_fallback_structure_for(flow_name: str, trigger_event: str) -> Optional[str]:
    fallbacks = _load_fallback_mappings()
    flow_map = fallbacks.get(flow_name, {})
    return flow_map.get(trigger_event)
