from __future__ import annotations

from functools import lru_cache
from importlib.resources import files
from typing import Dict, List


@lru_cache(maxsize=1)
def list_schema_groups() -> List[str]:
    groups: List[str] = []
    try:
        res_root = files("hl7_validation.resources")
        for item in res_root.iterdir():  # type: ignore[attr-defined]
            if item.is_dir():
                groups.append(item.name)
    except Exception:
        pass
    return sorted(set(groups))


@lru_cache(maxsize=64)
def list_schemas_for_group(flow_name: str) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    try:
        flow_dir = files("hl7_validation.resources") / flow_name
        for item in flow_dir.iterdir():  # type: ignore[attr-defined]
            if item.name.lower().endswith(".xsd"):
                trigger = item.stem
                mapping.setdefault(trigger, f"{flow_name}/{item.name}")
    except Exception:
        pass
    return mapping


def get_schema_xsd_path_for(flow_name: str, trigger_event: str) -> str:
    """Resolve on-disk path for the XSD mapped to flow + trigger event.

    - flow_name: e.g., 'phw', 'chemo', 'paris'
    - trigger_event: e.g., 'A31'
    """
    triggers = list_schemas_for_group(flow_name)
    xsd_rel = triggers.get(trigger_event)
    if not xsd_rel:
        available = ", ".join(sorted(triggers.keys())) or "<none>"
        raise ValueError(
            f"No XSD mapping for flow '{flow_name}' and trigger '{trigger_event}'. Available triggers: {available}"
        )
    return str(files("hl7_validation.resources") / xsd_rel)
